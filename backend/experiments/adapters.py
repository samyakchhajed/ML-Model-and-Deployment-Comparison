"""
experiments/adapters.py — All boto3 calls for the experiments Lambda.

Resource names are injected by Terraform as environment variables:
  ARTIFACTS_BUCKET        — S3 bucket for all experiment artifacts
  DYNAMODB_TABLE          — single DynamoDB table name
  USER_MODEL_WORKER_FN    — name of the pre-created user_model_worker Lambda
  SAGEMAKER_EXEC_ROLE     — IAM role ARN for SageMaker operations
  AWS_REGION              — injected automatically by the Lambda runtime
"""
import io
import os
import json
import tarfile
import tempfile

import boto3
from boto3.dynamodb.conditions import Attr

# ── Lazy-initialised AWS clients ─────────────────────────────────────────────────

_s3  = None
_ddb = None
_sm  = None

def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3

def _table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb").Table(os.environ["DYNAMODB_TABLE"])
    return _ddb

def _sagemaker():
    global _sm
    if _sm is None:
        _sm = boto3.client("sagemaker")
    return _sm


BUCKET       = os.environ.get("ARTIFACTS_BUCKET", "")
WORKER_FN    = os.environ.get("USER_MODEL_WORKER_FN", "ml-lab-user-model-worker")
SM_EXEC_ROLE = os.environ.get("SAGEMAKER_EXEC_ROLE", "")


# ── S3 helpers ────────────────────────────────────────────────────────────────────

def upload_csv(exp_id: str, filename: str, df) -> str:
    """Serialise a DataFrame to CSV and upload to S3. Returns s3:// URI."""
    key = f"{exp_id}/{filename}"
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    _s3_client().put_object(
        Bucket=BUCKET, Key=key,
        Body=buf.getvalue().encode("utf-8"),
        ContentType="text/csv",
    )
    return f"s3://{BUCKET}/{key}"


def upload_bytes(exp_id: str, filename: str, content: bytes, content_type: str) -> str:
    """Upload raw bytes to S3. Returns s3:// URI."""
    key = f"{exp_id}/{filename}"
    _s3_client().put_object(Bucket=BUCKET, Key=key, Body=content, ContentType=content_type)
    return f"s3://{BUCKET}/{key}"


def presigned_url(s3_uri: str, expires: int = 3600) -> str:
    """Return a pre-signed GET URL for an S3 object."""
    key = _key_from_uri(s3_uri)
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def _key_from_uri(s3_uri: str) -> str:
    return s3_uri.replace(f"s3://{BUCKET}/", "", 1)


# ── DynamoDB helpers ──────────────────────────────────────────────────────────────

def put_meta(exp_id: str, meta: dict) -> None:
    _table().put_item(Item={"PK": f"EXP#{exp_id}", "SK": "META", **meta})


def get_meta(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "META"})
    return r.get("Item")


def list_experiments() -> list:
    """Scan for all META records. Acceptable for a personal workbench scale."""
    result = _table().scan(FilterExpression=Attr("SK").eq("META"))
    items  = result.get("Items", [])
    rows   = []
    for meta in sorted(items, key=lambda x: x.get("created_at", ""), reverse=True):
        exp_id = meta["id"]
        rows.append({
            "id":           meta.get("id"),
            "name":         meta.get("name"),
            "target_col":   meta.get("target_col"),
            "problem_type": meta.get("problem_type"),
            "created_at":   meta.get("created_at"),
            "status":       meta.get("status"),
            "test_source":  meta.get("test_source"),
            "train_rows":   meta.get("train_rows"),
            "test_rows":    meta.get("test_rows"),
            "autopilot":    get_autopilot(exp_id) or {"job_name": None, "status": None, "candidates": []},
            "results":      get_results(exp_id),
        })
    return rows


def put_split(exp_id: str, train_uri: str, x_test_uri: str, y_test_uri: str) -> None:
    _table().put_item(Item={
        "PK":                   f"EXP#{exp_id}",
        "SK":                   "SPLIT",
        "train_s3_uri":         train_uri,
        "test_features_s3_uri": x_test_uri,
        "test_labels_s3_uri":   y_test_uri,
    })


def get_split(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "SPLIT"})
    return r.get("Item")


def put_model(exp_id: str, model: dict) -> None:
    _table().put_item(Item={"PK": f"EXP#{exp_id}", "SK": "MODEL", **model})


def get_model(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "MODEL"})
    item = r.get("Item")
    return _strip_keys(item) if item else None


def get_autopilot(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "AUTOPILOT"})
    item = r.get("Item")
    return _strip_keys(item) if item else None


def get_results(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "RESULTS"})
    item = r.get("Item")
    return _strip_keys(item) if item else None


def update_status(exp_id: str, status: str) -> None:
    _table().update_item(
        Key={"PK": f"EXP#{exp_id}", "SK": "META"},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status},
    )


def _strip_keys(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


# ── Lambda / SageMaker ────────────────────────────────────────────────────────────

def get_worker_fn_name() -> str:
    """The user_model_worker Lambda is pre-created by Terraform."""
    return WORKER_FN


def create_serverless_endpoint(exp_id: str, model_s3_uri: str) -> str:
    """
    1. Download the user's .pkl from S3.
    2. Bundle it with a standard SageMaker inference.py into a model.tar.gz.
    3. Upload the bundle to S3.
    4. Create a SageMaker Model + Serverless Endpoint Config + Endpoint.
    Returns the endpoint name (creation is async — poll via describe_endpoint).
    """
    pkl_bytes         = _download_s3_bytes(model_s3_uri)
    bundle_s3_uri     = _build_sagemaker_bundle(exp_id, pkl_bytes)
    model_name        = f"ml-lab-{exp_id}-model"
    config_name       = f"ml-lab-{exp_id}-epcfg"
    endpoint_name     = f"ml-lab-{exp_id}-ep"

    _sagemaker().create_model(
        ModelName=model_name,
        PrimaryContainer={
            "Image":        _sklearn_image_uri(),
            "ModelDataUrl": bundle_s3_uri,
            "Environment":  {"SAGEMAKER_PROGRAM": "inference.py"},
        },
        ExecutionRoleArn=SM_EXEC_ROLE,
    )

    _sagemaker().create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[{
            "VariantName": "default",
            "ModelName":   model_name,
            "ServerlessConfig": {
                "MemorySizeInMB": 2048,
                "MaxConcurrency":  5,
            },
        }],
    )

    _sagemaker().create_endpoint(
        EndpointName=endpoint_name,
        EndpointConfigName=config_name,
    )

    return endpoint_name


# ── Private helpers ───────────────────────────────────────────────────────────────

def _download_s3_bytes(s3_uri: str) -> bytes:
    key = _key_from_uri(s3_uri)
    obj = _s3_client().get_object(Bucket=BUCKET, Key=key)
    return obj["Body"].read()


def _build_sagemaker_bundle(exp_id: str, pkl_bytes: bytes) -> str:
    """Create model.tar.gz containing model.pkl + code/inference.py, upload to S3."""
    inference_py = _inference_script().encode("utf-8")

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        with tarfile.open(tmp.name, "w:gz") as tar:
            _tar_add_bytes(tar, pkl_bytes,    "model.pkl")
            _tar_add_bytes(tar, inference_py, "code/inference.py")
        tmp_path = tmp.name

    with open(tmp_path, "rb") as f:
        bundle_bytes = f.read()

    bundle_key = f"{exp_id}/sagemaker_model.tar.gz"
    _s3_client().put_object(
        Bucket=BUCKET, Key=bundle_key,
        Body=bundle_bytes,
        ContentType="application/gzip",
    )
    return f"s3://{BUCKET}/{bundle_key}"


def _tar_add_bytes(tar: tarfile.TarFile, data: bytes, arcname: str) -> None:
    info      = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _sklearn_image_uri() -> str:
    """AWS-managed SageMaker sklearn container. Region is injected by Lambda runtime."""
    region = os.environ.get("AWS_REGION", "ap-south-1")
    accounts = {
        "us-east-1":      "683313688378",
        "us-east-2":      "257758044811",
        "us-west-2":      "246618743249",
        "eu-west-1":      "141502667606",
        "ap-south-1":     "720646828776",
        "ap-southeast-1": "472281183178",
        "ap-southeast-2": "491556884379",
        "ap-northeast-1": "354813000052",
    }
    account = accounts.get(region, "720646828776")
    return (
        f"{account}.dkr.ecr.{region}.amazonaws.com"
        "/sagemaker-scikit-learn:1.2-1-cpu-py3"
    )


def _inference_script() -> str:
    """
    Standard SageMaker inference.py for scikit-learn .pkl models.
    Bundled into every user model .tar.gz at deploy time.
    """
    return '''\
import os, json, pickle
import numpy as np

def model_fn(model_dir):
    with open(os.path.join(model_dir, "model.pkl"), "rb") as f:
        return pickle.load(f)

def input_fn(request_body, content_type="application/json"):
    payload = json.loads(request_body)
    return np.array(payload["features"])

def predict_fn(input_data, model):
    return model.predict(input_data).tolist()

def output_fn(prediction, accept="application/json"):
    return json.dumps({"predictions": prediction}), accept
'''
