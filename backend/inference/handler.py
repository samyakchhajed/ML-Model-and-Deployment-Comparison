"""
inference/handler.py — Pure Python, no boto3.

API Gateway routes:
  POST /experiments/{id}/compare  → starts comparison, triggers async worker, returns 202
  GET  /experiments/{id}/results  → returns stored results (or null if still running)

Async worker route (invoked Lambda-to-Lambda with InvocationType='Event'):
  {"action": "worker", "exp_id": "..."}

Architecture
────────────
API Gateway has a hard 29-second response timeout. Running 5 Batch Transform jobs
sequentially or even in parallel can take 10–15 minutes. Therefore:

  1. POST /compare     → immediately fires an async self-invocation and returns 202
  2. Worker invocation → runs all inference jobs (up to Lambda's 15-min limit)
  3. GET /results      → frontend polls this until status == "completed"

The frontend must handle this async pattern:
  - On 202 response: show a "Processing..." state
  - Poll GET /experiments/{id} every ~10 seconds
  - Render results when exp.status == "completed"

Metrics computed (all via scikit-learn, no ROC-AUC):
  Classification: Accuracy, F1 (weighted), Precision (weighted), Recall (weighted)
  Regression:     R², RMSE, MAE, MAPE
"""
import io
import re
import json
import traceback
import concurrent.futures

import pandas as pd
import numpy as np
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    r2_score, mean_squared_error, mean_absolute_error,
    mean_absolute_percentage_error,
)

import adapters
from common.response import (
    ok, accepted, bad_request, not_found, server_error, options,
    get_method, get_path,
)


# ── Lambda entry point ───────────────────────────────────────────────────────────

def lambda_handler(event, context):
    # Async worker invocation (Lambda-to-Lambda, not from API Gateway)
    if event.get("action") == "worker":
        _run_worker(event["exp_id"])
        return {}

    # API Gateway request
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

    m = re.fullmatch(r"/experiments/(?P<id>[^/]+)/compare", path)
    if method == "POST" and m:
        return start_compare(m.group("id"))

    m = re.fullmatch(r"/experiments/(?P<id>[^/]+)/results", path)
    if method == "GET" and m:
        return get_results(m.group("id"))

    return not_found(f"No route for {method} {path}")


# ── Route handlers ───────────────────────────────────────────────────────────────

def start_compare(exp_id):
    meta      = adapters.get_meta(exp_id)
    model     = adapters.get_model(exp_id)
    autopilot = adapters.get_autopilot(exp_id)

    if not meta:
        return not_found(f"Experiment '{exp_id}' not found")

    has_deployed_model = bool(model and (model.get("lambda_fn_name") or model.get("sagemaker_serverless_endpoint")))
    has_autopilot_candidates = bool(autopilot and autopilot.get("candidates"))

    if not has_deployed_model and not has_autopilot_candidates:
        return bad_request("Deploy a model (to Lambda or SageMaker) or complete Autopilot before running comparison")

    # Clear any previous results and mark as running
    adapters.clear_results(exp_id)
    adapters.update_status(exp_id, "comparison_running")

    # Fire the async worker — returns immediately, Lambda continues in background
    adapters.invoke_self_async(exp_id)

    return accepted({
        "id":      exp_id,
        "status":  "comparison_running",
        "message": "Comparison started. Poll GET /experiments/{id}/results for progress.",
    })


def get_results(exp_id):
    meta    = adapters.get_meta(exp_id)
    results = adapters.get_results(exp_id)
    if not meta:
        return not_found(f"Experiment '{exp_id}' not found")
    return ok({"status": meta.get("status"), "results": results})


# ── Async worker ─────────────────────────────────────────────────────────────────

def _run_worker(exp_id: str) -> None:
    """
    Executes the full comparison pipeline:
    1. Load X_test and y_test from S3.
    2. Run Lambda + SageMaker inference for user model (if present).
    3. Run Batch Transform for all Autopilot candidates (if present, in parallel).
    4. Compute metrics against y_test.
    5. Store results + download URLs in DynamoDB.
    """
    try:
        meta      = adapters.get_meta(exp_id)
        model     = adapters.get_model(exp_id)
        split     = adapters.get_split(exp_id)
        autopilot = adapters.get_autopilot(exp_id)

        problem_type = meta["problem_type"]
        target_col   = meta["target_col"]

        # --- Load test data ------------------------------------------------------
        X_test_df = adapters.read_csv(split["test_features_s3_uri"])
        y_test_df = adapters.read_csv(split["test_labels_s3_uri"])
        y_true    = y_test_df[target_col].tolist()
        features  = X_test_df.values.tolist()
        feature_cols = X_test_df.columns.tolist()

        results = {
            "has_user_model":   False,
            "lambda_result":    None,
            "sagemaker_result": None,
            "candidate_results": [],
        }

        # --- User model inference paths ------------------------------------------
        has_model = bool(model and model.get("model_s3_uri"))
        if has_model:
            results["has_user_model"] = True

            # Path 1: Lambda
            if model.get("lambda_fn_name"):
                try:
                    lambda_preds = adapters.invoke_lambda(
                        model["lambda_fn_name"],
                        model["model_s3_uri"],
                        features,
                    )
                    results["lambda_result"] = {
                        "predictions":   lambda_preds,
                        "download_url":  adapters.presigned_url(model["model_s3_uri"]),
                        "metrics":       _compute_metrics(lambda_preds, y_true, problem_type),
                    }
                except Exception as e:
                    results["lambda_result"] = {"error": str(e)}

            # Path 2: SageMaker Serverless
            if model.get("sagemaker_serverless_endpoint"):
                try:
                    sm_preds = adapters.invoke_sagemaker_endpoint(
                        model["sagemaker_serverless_endpoint"],
                        X_test_df,
                    )
                    results["sagemaker_result"] = {
                        "predictions":  sm_preds,
                        "download_url": adapters.presigned_url(model["model_s3_uri"]),
                        "metrics":      _compute_metrics(sm_preds, y_true, problem_type),
                    }
                except Exception as e:
                    results["sagemaker_result"] = {"error": str(e)}

        # --- Autopilot candidate Batch Transform (parallel) if available ---------
        candidates = autopilot.get("candidates", []) if autopilot else []
        if candidates:
            candidate_results = _run_batch_transform_parallel(
                exp_id, candidates, split["test_features_s3_uri"], y_true, problem_type
            )
            results["candidate_results"] = candidate_results
        else:
            results["candidate_results"] = []

        # --- Best model ----------------------------------------------------------
        results["best_model"] = _find_best_model(results, problem_type)

        # --- Persist -------------------------------------------------------------
        adapters.put_results(exp_id, results)
        adapters.update_status(exp_id, "completed")

    except Exception as exc:
        traceback.print_exc()
        adapters.put_results(exp_id, {"error": str(exc)})
        adapters.update_status(exp_id, "comparison_failed")


# ── Batch Transform — parallel ────────────────────────────────────────────────────

def _run_batch_transform_parallel(
    exp_id: str,
    candidates: list,
    x_test_s3_uri: str,
    y_true: list,
    problem_type: str,
) -> list:
    """
    Starts all candidate Batch Transform jobs simultaneously, waits for all of
    them to finish (using threads for parallel polling), then reads predictions.
    Safe within Lambda's 15-minute timeout for typical small test datasets.
    """
    results = [None] * len(candidates)

    def _process_one(idx_candidate):
        idx, candidate = idx_candidate
        try:
            job_name = adapters.start_batch_transform(
                exp_id       = exp_id,
                candidate_idx= idx,
                model_s3_uri = candidate["model_s3_uri"],
                input_s3_uri = x_test_s3_uri,
            )
            adapters.wait_for_batch_transform(job_name)
            preds = adapters.read_batch_transform_output(exp_id, idx)

            metrics = _compute_metrics(preds, y_true, problem_type)

            return idx, {
                "name":         candidate["name"],
                "algorithm":    candidate["algorithm"],
                "predictions":  preds,
                "metrics":      metrics,
                "download_url": adapters.presigned_url(candidate["model_s3_uri"]),
                "model_s3_uri": candidate["model_s3_uri"],
            }
        except Exception as e:
            traceback.print_exc()
            return idx, {
                "name":      candidate.get("name", f"candidate-{idx}"),
                "algorithm": candidate.get("algorithm", "Unknown"),
                "error":     str(e),
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(_process_one, (i, c)) for i, c in enumerate(candidates)]
        for fut in concurrent.futures.as_completed(futures):
            idx, res = fut.result()
            results[idx] = res

    return [r for r in results if r is not None]


# ── Metric computation ────────────────────────────────────────────────────────────

def _compute_metrics(predictions: list, y_true: list, problem_type: str) -> dict:
    """
    Compute evaluation metrics by comparing predictions against ground truth.

    Classification: Accuracy, F1 (weighted), Precision (weighted), Recall (weighted)
    Regression:     R², RMSE, MAE, MAPE
    """
    y_pred = np.array(predictions)
    y_real = np.array(y_true)

    if problem_type == "classification":
        return {
            "accuracy":  round(float(accuracy_score(y_real, y_pred)), 4),
            "f1":        round(float(f1_score(y_real, y_pred, average="weighted", zero_division=0)), 4),
            "precision": round(float(precision_score(y_real, y_pred, average="weighted", zero_division=0)), 4),
            "recall":    round(float(recall_score(y_real, y_pred, average="weighted", zero_division=0)), 4),
        }
    else:  # regression
        mse  = float(mean_squared_error(y_real, y_pred))
        return {
            "r2":   round(float(r2_score(y_real, y_pred)), 4),
            "rmse": round(float(mse ** 0.5), 4),
            "mae":  round(float(mean_absolute_error(y_real, y_pred)), 4),
            "mape": round(float(mean_absolute_percentage_error(y_real, y_pred)), 4),
        }


# ── Best model selection ─────────────────────────────────────────────────────────

def _find_best_model(results: dict, problem_type: str) -> dict | None:
    """
    Rank all models by the primary metric and return the winner.
    Primary metric: Accuracy (classification) | R² (regression).
    Higher is better for both.
    """
    primary = "accuracy" if problem_type == "classification" else "r2"
    contenders = []

    def _add(name, label, result):
        if result and not result.get("error") and result.get("metrics"):
            score = result["metrics"].get(primary)
            if score is not None:
                contenders.append({"name": name, "label": label, "score": score, "metrics": result["metrics"]})

    _add("lambda",    "Lambda",                results.get("lambda_result"))
    _add("sagemaker", "SageMaker Serverless",  results.get("sagemaker_result"))
    for c in results.get("candidate_results", []):
        _add(c["name"], f"Autopilot — {c['algorithm']}", c)

    if not contenders:
        return None

    best = max(contenders, key=lambda x: x["score"])
    return {
        "name":    best["name"],
        "label":   best["label"],
        "metric":  primary,
        "score":   best["score"],
        "metrics": best["metrics"],
    }
