"""
autopilot/adapters.py — All boto3 calls for the autopilot Lambda.

Environment variables injected by Terraform:
  ARTIFACTS_BUCKET     — S3 bucket
  DYNAMODB_TABLE       — DynamoDB table name
  AUTOPILOT_OUTPUT_S3  — S3 prefix for Autopilot output artifacts
  SAGEMAKER_EXEC_ROLE  — IAM role ARN
"""
import os

import boto3
from boto3.dynamodb.conditions import Attr

BUCKET          = os.environ.get("ARTIFACTS_BUCKET", "")
TABLE           = os.environ.get("DYNAMODB_TABLE", "")
AUTOPILOT_OUT   = os.environ.get("AUTOPILOT_OUTPUT_S3", "autopilot-output")
SM_EXEC_ROLE    = os.environ.get("SAGEMAKER_EXEC_ROLE", "")

_sm  = None
_ddb = None

def _sagemaker():
    global _sm
    if _sm is None:
        _sm = boto3.client("sagemaker")
    return _sm

def _table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb").Table(TABLE)
    return _ddb


# ── SageMaker Autopilot ───────────────────────────────────────────────────────────

def start_autopilot_job(exp_id: str, train_s3_uri: str, target_col: str, problem_type: str) -> str:
    """
    Launch a SageMaker Autopilot job capped at 5 candidates.
    The job reads from the training split S3 URI produced at dataset upload time.
    Returns the job name.
    """
    # SageMaker AutoMLJobName max length is 32 chars: ^[a-zA-Z0-9](-*[a-zA-Z0-9]){0,31}$
    clean_id    = exp_id.replace("-", "")[:24]
    job_name    = f"ap-{clean_id}"
    output_path = f"s3://{BUCKET}/{AUTOPILOT_OUT}/{exp_id}/"

    # S3DataSource requires an S3 prefix pointing to the folder containing the CSV
    train_prefix = train_s3_uri if train_s3_uri.endswith("/") else train_s3_uri.rsplit("/", 1)[0] + "/"

    kwargs = {
        "AutoMLJobName": job_name,
        "InputDataConfig": [{
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri":      train_prefix,
                }
            },
            "TargetAttributeName": target_col,
            "ContentType":         "text/csv",
        }],
        "OutputDataConfig": {"S3OutputPath": output_path},
        "AutoMLJobConfig": {
            "CompletionCriteria": {"MaxCandidates": 5},
        },
        "RoleArn": SM_EXEC_ROLE,
    }
    if problem_type == "regression":
        kwargs["ProblemType"] = "Regression"

    _sagemaker().create_auto_ml_job(**kwargs)
    return job_name


def describe_autopilot_job(job_name: str) -> tuple[str, list]:
    """
    Poll the Autopilot job. Returns (status, candidates).
    candidates is populated only when status == "Completed".
    """
    response = _sagemaker().describe_auto_ml_job(AutoMLJobName=job_name)
    status   = response["AutoMLJobStatus"]  # InProgress | Completed | Failed | Stopped

    candidates = []
    if status == "Completed":
        resp = _sagemaker().list_candidates_for_auto_ml_job(
            AutoMLJobName=job_name,
            SortBy="FinalObjectiveMetricValue",
            SortOrder="Descending",
            MaxResults=5,
        )
        for c in resp.get("Candidates", []):
            # Model artifact lives in the first inference container
            containers = c.get("InferenceContainers", [])
            model_uri  = containers[0].get("ModelDataUrl", "") if containers else ""
            candidates.append({
                "name":         c["CandidateName"],
                "algorithm":    _extract_algorithm(c),
                "model_s3_uri": model_uri,
                "status":       c.get("CandidateStatus", ""),
            })

    return status, candidates


def _problem_type_map(problem_type: str) -> str:
    mapping = {
        "classification": "BinaryClassification",
        "regression":     "Regression",
    }
    return mapping.get(problem_type, "BinaryClassification")


def _extract_algorithm(candidate: dict) -> str:
    """Best-effort algorithm name extracted from the Autopilot candidate step names."""
    steps = candidate.get("CandidateSteps", [])
    known = ["XGBoost", "LightGBM", "RandomForest", "LinearLearner",
             "AutoGluon", "CatBoost", "MLP", "Linear"]
    for step in reversed(steps):
        step_name = step.get("CandidateStepName", "").lower()
        for algo in known:
            if algo.lower() in step_name:
                return algo
    return "AutoML"


# ── DynamoDB helpers ──────────────────────────────────────────────────────────────

def get_meta(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "META"})
    return r.get("Item")


def get_split(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "SPLIT"})
    return r.get("Item")


def get_autopilot(exp_id: str) -> dict | None:
    r = _table().get_item(Key={"PK": f"EXP#{exp_id}", "SK": "AUTOPILOT"})
    item = r.get("Item")
    return {k: v for k, v in item.items() if k not in ("PK", "SK")} if item else None


def put_autopilot(exp_id: str, record: dict) -> None:
    _table().put_item(Item={"PK": f"EXP#{exp_id}", "SK": "AUTOPILOT", **record})


def update_status(exp_id: str, status: str) -> None:
    _table().update_item(
        Key={"PK": f"EXP#{exp_id}", "SK": "META"},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status},
    )
