"""
experiments/handler.py — Pure Python, no boto3.

Routes handled (via API Gateway → this Lambda):
  GET    /experiments
  POST   /experiments               ← dataset CSV + optional test CSV + optional model
  GET    /experiments/{id}
  POST   /experiments/{id}/model    ← .pkl upload
  POST   /experiments/{id}/deploy/lambda
  POST   /experiments/{id}/deploy/sagemaker
"""
import io
import json
import re
import uuid
import datetime
import traceback

import pandas as pd
from sklearn.model_selection import train_test_split

import adapters
from common.response import (
    ok, accepted, created, bad_request, not_found, server_error, options,
    get_method, get_path,
)
from common.multipart import parse_multipart


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

    if method == "GET"  and re.fullmatch(r"/experiments", path):
        return list_experiments()

    if method == "POST" and re.fullmatch(r"/experiments", path):
        return create_experiment(event)

    m = re.fullmatch(r"/experiments/(?P<id>[^/]+)", path)
    if method == "GET" and m:
        return get_experiment(m.group("id"))

    m = re.fullmatch(r"/experiments/(?P<id>[^/]+)/model", path)
    if method == "POST" and m:
        return upload_model(event, m.group("id"))

    m = re.fullmatch(r"/experiments/(?P<id>[^/]+)/deploy/lambda", path)
    if method == "POST" and m:
        return deploy_lambda(m.group("id"))

    m = re.fullmatch(r"/experiments/(?P<id>[^/]+)/deploy/sagemaker", path)
    if method == "POST" and m:
        return deploy_sagemaker(m.group("id"))

    return not_found(f"No route for {method} {path}")


# ── Route handlers ───────────────────────────────────────────────────────────────

def list_experiments():
    return ok({"experiments": adapters.list_experiments()})


def create_experiment(event):
    fields, files = parse_multipart(event)

    # --- Validate required fields -----------------------------------------------
    name         = fields.get("name", "").strip()
    target_col   = fields.get("target_col", "").strip()
    problem_type = fields.get("problem_type", "").strip()

    if not name:
        return bad_request("'name' is required")
    if not target_col:
        return bad_request("'target_col' is required")
    if problem_type not in ("classification", "regression"):
        return bad_request("'problem_type' must be 'classification' or 'regression'")
    if "file" not in files:
        return bad_request("Dataset CSV ('file') is required")

    exp_id = f"exp-{uuid.uuid4().hex[:8]}"
    now    = datetime.datetime.utcnow().isoformat() + "Z"

    # --- Load dataset ------------------------------------------------------------
    dataset_bytes = files["file"]["content"]
    try:
        df = pd.read_csv(io.BytesIO(dataset_bytes))
    except Exception as exc:
        return bad_request(f"Could not parse dataset CSV: {exc}")

    if target_col not in df.columns:
        return bad_request(f"Target column '{target_col}' not found. Columns: {list(df.columns)}")

    # --- Determine train / test split -------------------------------------------
    test_file = files.get("test_csv")
    if test_file:
        # User supplied a separate labeled test CSV — primary path
        try:
            test_df = pd.read_csv(io.BytesIO(test_file["content"]))
        except Exception as exc:
            return bad_request(f"Could not parse test CSV: {exc}")

        if target_col not in test_df.columns:
            return bad_request(f"Target column '{target_col}' not found in test CSV")

        train_df    = df                           # full dataset goes to Autopilot
        X_test      = test_df.drop(columns=[target_col])
        y_test      = test_df[[target_col]]
        test_source = "user_supplied"
    else:
        # Fallback: automatic 80/20 split
        train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)
        X_test      = test_df.drop(columns=[target_col])
        y_test      = test_df[[target_col]]
        test_source = "auto_split"

    # --- Upload splits to S3 (train isolated for Autopilot S3Prefix) ------------
    dataset_uri  = adapters.upload_csv(exp_id, "dataset.csv",         df)
    train_uri    = adapters.upload_csv(exp_id, "train/train.csv",     train_df)
    x_test_uri   = adapters.upload_csv(exp_id, "test_features.csv",   X_test)
    y_test_uri   = adapters.upload_csv(exp_id, "test_labels.csv",     y_test)

    # --- Optional model upload at creation time ---------------------------------
    model_record = None
    if "model" in files:
        model_bytes  = files["model"]["content"]
        model_uri    = adapters.upload_bytes(exp_id, "model.pkl", model_bytes, "application/octet-stream")
        model_record = {"model_s3_uri": model_uri, "lambda_fn_name": None, "sagemaker_serverless_endpoint": None}
        adapters.put_model(exp_id, model_record)

    # --- Persist to DynamoDB ----------------------------------------------------
    meta = {
        "id":             exp_id,
        "name":           name,
        "target_col":     target_col,
        "problem_type":   problem_type,
        "created_at":     now,
        "status":         "model_uploaded" if model_record else "created",
        "dataset_s3_uri": dataset_uri,
        "test_source":    test_source,
        "train_rows":     len(train_df),
        "test_rows":      len(X_test),
    }
    adapters.put_meta(exp_id, meta)
    adapters.put_split(exp_id, train_uri, x_test_uri, y_test_uri)

    return created(_assemble(exp_id, meta, model_record, None, None))


def get_experiment(exp_id):
    meta = adapters.get_meta(exp_id)
    if not meta:
        return not_found(f"Experiment '{exp_id}' not found")

    model     = adapters.get_model(exp_id)
    autopilot = adapters.get_autopilot(exp_id)
    results   = adapters.get_results(exp_id)
    return ok(_assemble(exp_id, meta, model, autopilot, results))


def upload_model(event, exp_id):
    meta = adapters.get_meta(exp_id)
    if not meta:
        return not_found(f"Experiment '{exp_id}' not found")

    _, files = parse_multipart(event)
    if "file" not in files:
        return bad_request("Model file ('file') is required")

    model_bytes  = files["file"]["content"]
    model_uri    = adapters.upload_bytes(exp_id, "model.pkl", model_bytes, "application/octet-stream")
    model_record = {"model_s3_uri": model_uri, "lambda_fn_name": None, "sagemaker_serverless_endpoint": None}
    adapters.put_model(exp_id, model_record)
    adapters.update_status(exp_id, "model_uploaded")
    meta["status"] = "model_uploaded"

    return ok(_assemble(exp_id, meta, model_record, adapters.get_autopilot(exp_id), None))


def deploy_lambda(exp_id):
    """
    Mark the experiment as Lambda-deployed. The user_model_worker Lambda is
    pre-created by Terraform; we just record its name so the inference Lambda
    knows where to route calls.
    """
    meta  = adapters.get_meta(exp_id)
    model = adapters.get_model(exp_id)
    if not meta:
        return not_found(f"Experiment '{exp_id}' not found")
    if not model or not model.get("model_s3_uri"):
        return bad_request("Upload a model before deploying to Lambda")

    model["lambda_fn_name"] = adapters.get_worker_fn_name()
    adapters.put_model(exp_id, model)
    adapters.update_status(exp_id, "lambda_deployed")
    meta["status"] = "lambda_deployed"

    return ok(_assemble(exp_id, meta, model, adapters.get_autopilot(exp_id), None))


def deploy_sagemaker(exp_id):
    """
    Package the user's .pkl into a SageMaker-compatible model artifact and
    create a Serverless Inference endpoint. Returns once the endpoint is
    CREATING — the frontend polls GET /experiments/{id} for the final status.
    """
    meta  = adapters.get_meta(exp_id)
    model = adapters.get_model(exp_id)
    if not meta:
        return not_found(f"Experiment '{exp_id}' not found")
    if not model or not model.get("model_s3_uri"):
        return bad_request("Upload a model before deploying to SageMaker")

    endpoint_name = adapters.create_serverless_endpoint(exp_id, model["model_s3_uri"])
    model["sagemaker_serverless_endpoint"] = endpoint_name
    adapters.put_model(exp_id, model)
    adapters.update_status(exp_id, "sagemaker_deployed")
    meta["status"] = "sagemaker_deployed"

    return ok(_assemble(exp_id, meta, model, adapters.get_autopilot(exp_id), None))


# ── Response assembler ───────────────────────────────────────────────────────────

def _assemble(exp_id, meta, model, autopilot, results):
    return {
        "id":           exp_id,
        "name":         meta.get("name"),
        "target_col":   meta.get("target_col"),
        "problem_type": meta.get("problem_type"),
        "created_at":   meta.get("created_at"),
        "status":       meta.get("status"),
        "test_source":  meta.get("test_source"),
        "train_rows":   meta.get("train_rows"),
        "test_rows":    meta.get("test_rows"),
        "model":        model,
        "autopilot":    autopilot or {"job_name": None, "status": None, "candidates": []},
        "results":      results,
    }
