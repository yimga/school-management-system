"""
RunMyCampus SDK stub: minimal API client and auth helper for integration.
"""
from runmycampus.client import RunMyCampusClient
from runmycampus.webhooks import (
    canonical_json_bytes,
    sign_payload,
    verify_webhook_signature,
)

__all__ = [
    "RunMyCampusClient",
    "canonical_json_bytes",
    "sign_payload",
    "verify_webhook_signature",
]
