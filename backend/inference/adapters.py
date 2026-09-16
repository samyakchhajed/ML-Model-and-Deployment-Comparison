"""
inference/adapters.py — All boto3 calls for the inference Lambda.

Environment variables (injected by Terraform):
  ARTIFACTS_BUCKET         — S3 bucket for all experiment artifacts
  DYNAMODB_TABLE           — DynamoDB table name
  BATCH_TRANSFORM_ROLE     — IAM role ARN for Batch Transform jobs
  BATCH_OUTPUT_PREFIX      — S3 prefix for Batch Transform output
  AWS_LAMBDA_FUNCTION_NAME — auto-injected by Lambda runtime (used for self-invocation)
"""
import io
import os
import json
import time

import boto3
import pandas as pd
from boto3.dynamodb.conditions import Attr

BUCKET              = os.environ.get("ARTIFACTS_BUCKET", "")
TABLE               = os.environ.get("DYNAMODB_TABLE", "")
BATCH_ROLE          = os.environ.get("BATCH_TRANSFORM_ROLE", "")
BATCH_OUT_PREFIX    = os.environ.get("BATCH_OUTPUT_PREFIX", "batch-output")
SELF_FN_NAME        = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")

# Lazy-initialised clients
_s3    = None
_ddb   = None
_sm    = None
_smrt  = None
_lmb   = None

def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3

def _table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb").Table(TABLE)
    return _ddb

def _sagemaker():
    global _sm
    if _sm is None:
        _sm = boto3.client("sagemaker")
    return _sm

def _sagemaker_runtime():
    global _smrt
    if _smrt is None:
        _smrt = boto3.client("sagemaker-runtime")
    return _smrt

def _lambda_client():
    global _lmb
    if _lmb is None:
        _lmb = boto3.client("lambda")
    return _lmb


# ── Self-invocation (async worker trigger) ────────────────────────────────────────

def invoke_self_async(exp_id: str) -> None:
    """
    Invoke this same Lambda function asynchronously with the worker payload.
    InvocationType='Event' means fire-and-forget — returns immediately.
    """
    _lambda_client().invoke(
        FunctionName=SELF_FN_NAME,
        InvocationType="Event",
        Payload=json.dumps({"action": "worker", "exp_id": exp_id}).encode(),
    )


# ── S3 helpers ────────────────────────────────────────────────────────────────────

def read_csv(s3_uri: str) -> pd.DataFrame:
    key  = _key_from_uri(s3_uri)
    obj  = _s3_client().get_object(Bucket=BUCKET, Key=key)
    return pd.read_csv(io.BytesIO(obj["Body"].read()))


def presigned_url(s3_uri: str, expires: int = 3600) -> str:
    key = _key_from_uri(s3_uri)
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def _key_from_uri(s3_uri: str) -> str:
    return s3_uri.replace(f"s3://{BUCKET}/", "", 1)


# ── Lambda invoke (user_model_worker) ─────────────────────────────────────────────

def invoke_lambda(fn_name: str, model_s3_uri: str, features: list) -> list:
    """
    Invoke the user_model_worker Lambda synchronously.
    Payload: {"model_s3_uri": "...", "features": [[...]]}
    Returns list of predictions.
    """
    payload = json.dumps({"model_s3_uri": model_s3_uri, "features": features}).encode()
    response = _lambda_client().invoke(
        FunctionName=fn_name,
        InvocationType="RequestResponse",
        Payload=payload,
    )
    result = json.loads(response["Payload"].read())
    if "errorMessage" in result:
        raise RuntimeError(f"user_model_worker error: {result['errorMessage']}")
    return result["predictions"]


# ── SageMaker Serverless Inference ────────────────────────────────────────────────

def invoke_sagemaker_endpoint(endpoint_name: str, X_test_df: pd.DataFrame) -> list:
    """
    Invoke a SageMaker Serverless endpoint with feature rows as JSON.
    The endpoint uses the inference.py bundled at deploy time.
    """
    payload = json.dumps({"features": X_test_df.values.tolist()})
    response = _sagemaker_runtime().invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Accept="application/json",
        Body=payload.encode(),
    )
    result = json.loads(response["Body"].read())
    return result["predictions"]


# ── SageMaker Batch Transform ─────────────────────────────────────────────────────

def start_batch_transform(
    exp_id: str,
    candidate_idx: int,
    model_s3_uri: str,
    input_s3_uri: str,
) -> str:
    """
    Create a SageMaker Batch Transform job for one Autopilot candidate.
    Returns the job name.
    """
    job_name   = f"ml-lab-bt-{exp_id}-c{candidate_idx}"
    model_name = f"ml-lab-bt-model-{exp_id}-c{candidate_idx}"
    output_s3  = f"s3://{BUCKET}/{BATCH_OUT_PREFIX}/{exp_id}/candidate-{candidate_idx}/"

    # Create a temporary SageMaker Model from the candidate artifact
    _sagemaker().create_model(
        ModelName=model_name,
        PrimaryContainer={"ModelDataUrl": model_s3_uri},
        ExecutionRoleArn=BATCH_ROLE,
    )

    _sagemaker().create_transform_job(
        TransformJobName=job_name,
        ModelName=model_name,
        TransformInput={
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri":      input_s3_uri,
                }
            },
            "ContentType": "text/csv",
            "SplitType":   "Line",
        },
        TransformOutput={
            "S3OutputPath": output_s3,
            "AssembleWith": "Line",
        },
        TransformResources={
            "InstanceType":  "ml.m5.large",
            "InstanceCount":  1,
        },
    )
    return job_name


def wait_for_batch_transform(job_name: str, poll_interval: int = 30) -> None:
    """
    Block until the Batch Transform job reaches a terminal state.
    Raises RuntimeError if the job fails.
    """
    while True:
        response = _sagemaker().describe_transform_job(TransformJobName=job_name)
        status   = response["TransformJobStatus"]  # InProgress | Completed | Failed | Stopped
        if status == "Completed":
            return
        if status in ("Failed", "Stopped"):
            reason = response.get("FailureReason", "Unknown reason")
            raise RuntimeError(f"Batch Transform job '{job_name}' ended with status '{status}': {reason}")
        time.sleep(poll_interval)


def read_batch_transform_output(exp_id: str, candidate_idx: int) -> list:
    """
    Read the Batch Transform output CSV from S3 and return predictions as a list.
    SageMaker Batch Transform writes one prediction per line.
    """
    prefix = f"{BATCH_OUT_PREFIX}/{exp_id}/candidate-{candidate_idx}/"
    response = _s3_client().list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    contents = response.get("Contents", [])
    if not contents:
        raise RuntimeError(f"No Batch Transform output found at s3://{BUCKET}/{prefix}")

    # There is usually one output file; concatenate if there are more
    all_preds = []
    for obj in sorted(contents, key=lambda x: x["Key"]):
        raw   = _s3_client().get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read()
        lines = raw.decode("utf-8").strip().splitlines()
        for line in lines:
            line = line.strip()
            if line:
                try:
                    all_preds.append(float(line) if "." in line else int(line))
                except ValueError:
                    all_preds.append(line)

    return all_preds


# ── DynamoDB helpers ──────────────────────────────────────────────────────────────

def get_meta(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "META"})
    return r.get("Item")


def get_model(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "MODEL"})
    item = r.get("Item")
    return _strip_keys(item) if item else None


def get_split(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "SPLIT"})
    return r.get("Item")


def get_autopilot(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "AUTOPILOT"})
    item = r.get("Item")
    return _strip_keys(item) if item else None


def get_results(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "RESULTS"})
    item = r.get("Item")
    return _strip_keys(item) if item else None


def put_results(exp_id: str, results: dict) -> None:
    _table().put_item(Item={"PK": f"EXP#{exp_id}", "SK": "RESULTS", **results})


def clear_results(exp_id: str) -> None:
    try:
        _table().delete_item(Key={"PK": f"EXP#{exp_id}", "SK": "RESULTS"})
    except Exception:
        pass


def update_status(exp_id: str, status: str) -> None:
    _table().update_item(
        Key={"PK": f"EXP#{exp_id}", "SK": "META"},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status},
    )


def _strip_keys(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}
