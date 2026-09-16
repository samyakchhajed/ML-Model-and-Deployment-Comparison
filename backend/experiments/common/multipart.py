"""
common/multipart.py — Parse multipart/form-data from API Gateway proxy events.
"""
import base64
import email.parser
import email.policy


def parse_multipart(event: dict) -> tuple[dict, dict]:
    """
    Parse a multipart/form-data API Gateway event.

    Returns
    -------
    fields : dict[str, str]   — plain text form fields
    files  : dict[str, dict]  — uploaded files, each has {"filename": str, "content": bytes}
    """
    body: bytes
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded", False):
        body = base64.b64decode(raw_body)
    else:
        body = raw_body.encode("utf-8")

    headers = event.get("headers") or {}
    content_type = (
        headers.get("Content-Type")
        or headers.get("content-type")
        or ""
    )

    raw = b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
    msg = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(raw)

    fields: dict[str, str]  = {}
    files:  dict[str, dict] = {}

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue

        disposition = part.get("Content-Disposition", "")
        if not disposition:
            continue

        params: dict[str, str] = {}
        for segment in disposition.split(";")[1:]:
            segment = segment.strip()
            if "=" in segment:
                k, v = segment.split("=", 1)
                params[k.strip()] = v.strip().strip('"')

        name     = params.get("name", "")
        filename = params.get("filename", "")
        content  = part.get_payload(decode=True) or b""

        if filename:
            files[name] = {"filename": filename, "content": content}
        else:
            fields[name] = content.decode("utf-8", errors="replace")

    return fields, files
