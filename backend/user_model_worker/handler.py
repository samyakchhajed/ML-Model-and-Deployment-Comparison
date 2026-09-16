"""
user_model_worker/handler.py — Standalone Lambda for user model (.pkl) inference.

Not exposed via API Gateway. Invoked directly by the inference Lambda
(InvocationType='RequestResponse') with:

  {
    "model_s3_uri": "s3://bucket/exp-id/model.pkl",
    "features":     [[1.0, 2.0, ...], [3.0, 4.0, ...], ...]
  }

Returns:
  {
    "predictions": [1, 0, 1, ...]   (classification)
    "predictions": [1.23, 4.56, ...]  (regression)
  }

The model is cached in /tmp across warm Lambda invocations so subsequent
calls within the same container reuse the loaded model (no repeated S3 download).
"""
import os
import io
import json
import pickle
import hashlib
import traceback

import numpy as np
import boto3

_s3    = None
_cache = {}   # {model_s3_uri: model_object}

def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3

BUCKET = os.environ.get("ARTIFACTS_BUCKET", "")


def lambda_handler(event, context):
    try:
        model_s3_uri: str  = event["model_s3_uri"]
        features:     list = event["features"]

        model = _load_model(model_s3_uri)
        X     = np.array(features)
        preds = model.predict(X).tolist()

        return {"predictions": preds}

    except Exception as exc:
        traceback.print_exc()
        # Returning errorMessage causes the inference Lambda to detect and re-raise
        return {"errorMessage": str(exc), "errorType": type(exc).__name__}


def _load_model(s3_uri: str):
    """
    Return a cached model if available, otherwise download from S3.
    Cache is keyed by S3 URI — safe because models are immutable after upload.
    """
    if s3_uri in _cache:
        return _cache[s3_uri]

    local_path = _maybe_cache_to_disk(s3_uri)
    with open(local_path, "rb") as f:
        model = pickle.load(f)

    _cache[s3_uri] = model
    return model


def _maybe_cache_to_disk(s3_uri: str) -> str:
    """
    Download the model .pkl to /tmp (only if not already there).
    Uses a hash of the URI as the filename to avoid collisions.
    """
    uri_hash   = hashlib.md5(s3_uri.encode()).hexdigest()[:12]
    local_path = f"/tmp/model_{uri_hash}.pkl"

    if not os.path.exists(local_path):
        key = s3_uri.replace(f"s3://{BUCKET}/", "", 1)
        obj = _s3_client().get_object(Bucket=BUCKET, Key=key)
        with open(local_path, "wb") as f:
            f.write(obj["Body"].read())

    return local_path
