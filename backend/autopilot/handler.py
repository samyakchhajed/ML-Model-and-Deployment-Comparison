"""
autopilot/handler.py — Pure Python, no boto3.

Routes:
  POST /experiments/{id}/autopilot/start
  GET  /experiments/{id}/autopilot/status
"""
import re
import traceback

import adapters
from common.response import (
    ok, bad_request, not_found, server_error, options,
    get_method, get_path,
)


# ── Lambda entry point ───────────────────────────────────────────────────────────

def lambda_handler(event, context):
    method = get_method(event)
    if method == "OPTIONS":
        return options()
    try:
        return _route(event)
    except Exception as exc:
        traceback.print_exc()
        return server_error(str(exc))


# ── Router ───────────────────────────────────────────────────────────────────────

def _route(event):
    method = get_method(event)
    path   = get_path(event)

    m = re.fullmatch(r"/experiments/(?P<id>[^/]+)/autopilot/start", path)
    if method == "POST" and m:
        return start_autopilot(m.group("id"))

    m = re.fullmatch(r"/experiments/(?P<id>[^/]+)/autopilot/status", path)
    if method == "GET" and m:
        return get_status(m.group("id"))

    return not_found(f"No route for {method} {path}")


# ── Route handlers ───────────────────────────────────────────────────────────────

def start_autopilot(exp_id):
    meta  = adapters.get_meta(exp_id)
    split = adapters.get_split(exp_id)

    if not meta:
        return not_found(f"Experiment '{exp_id}' not found")
    if not split or not split.get("train_s3_uri"):
        return bad_request("Training data not found — upload a dataset first")

    existing = adapters.get_autopilot(exp_id)
    if existing and existing.get("status") in ("InProgress", "Completed"):
        return bad_request(f"Autopilot job already exists (status: {existing['status']})")

    job_name = adapters.start_autopilot_job(
        exp_id       = exp_id,
        train_s3_uri = split["train_s3_uri"],
        target_col   = meta["target_col"],
        problem_type = meta["problem_type"],
    )

    record = {"job_name": job_name, "status": "InProgress", "candidates": []}
    adapters.put_autopilot(exp_id, record)
    adapters.update_status(exp_id, "autopilot_running")

    return ok({"id": exp_id, "autopilot": record})


def get_status(exp_id):
    stored = adapters.get_autopilot(exp_id)
    if not stored or not stored.get("job_name"):
        return ok({"status": None, "candidates": []})

    # If already completed locally, return cached result — avoid unnecessary API calls
    if stored.get("status") == "Completed" and stored.get("candidates"):
        return ok({"status": "Completed", "candidates": stored["candidates"]})

    live_status, candidates = adapters.describe_autopilot_job(stored["job_name"])

    # Persist updates only when something changed
    changed = (
        live_status != stored.get("status")
        or (candidates and candidates != stored.get("candidates", []))
    )
    if changed:
        stored["status"]     = live_status
        stored["candidates"] = candidates
        adapters.put_autopilot(exp_id, stored)
        if live_status == "Completed":
            adapters.update_status(exp_id, "autopilot_done")
        elif live_status == "Failed":
            adapters.update_status(exp_id, "autopilot_failed")

    return ok({"status": live_status, "candidates": candidates})
