"""Verify outbound webhook signatures (matches server ``apps.events.webhooks.sign_payload``)."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_payload(secret: str, payload_bytes: bytes) -> str:
    digest = hmac.new(
        (secret or "").encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


def verify_webhook_signature(
    secret: str, body: bytes, x_webhook_signature: str
) -> bool:
    """
    Constant-time compare of ``X-Webhook-Signature`` header to HMAC-SHA256 of body.
    """
    if not x_webhook_signature or not body:
        return False
    expected = sign_payload(secret, body)
    return hmac.compare_digest(expected.strip(), (x_webhook_signature or "").strip())
