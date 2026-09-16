"""
common/response.py — Standard API Gateway JSON response builder and request normalizer.
Included in every Lambda ZIP by Terraform packaging.
"""
import json

_CORS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}

def get_method(event: dict) -> str:
    """Extract HTTP method supporting both API Gateway Payload Format 1.0 and 2.0."""
    return (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method")
        or ""
    ).upper()

def get_path(event: dict) -> str:
    """Extract path supporting both API Gateway Payload Format 1.0 and 2.0."""
    return (
        event.get("path")
        or event.get("rawPath")
        or ""
    ).rstrip("/")

def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers":    {**_CORS, "Content-Type": "application/json"},
        "body":       json.dumps(body, default=str),
    }

def ok(body: dict = None) -> dict:
    return _resp(200, body or {})

def accepted(body: dict = None) -> dict:
    return _resp(202, body or {})

def created(body: dict = None) -> dict:
    return _resp(201, body or {})

def bad_request(message: str) -> dict:
    return _resp(400, {"error": message})

def not_found(message: str = "Not found") -> dict:
    return _resp(404, {"error": message})

def server_error(message: str = "Internal server error") -> dict:
    return _resp(500, {"error": message})

def options() -> dict:
    """Handle CORS preflight OPTIONS request."""
    return {"statusCode": 200, "headers": _CORS, "body": ""}
