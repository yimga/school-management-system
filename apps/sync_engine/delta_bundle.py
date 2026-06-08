"""Signed NDJSON delta bundles for LAN data-mule sync (SODP batch 1412)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Iterator

from django.conf import settings

from apps.sync_engine.policy_registry import POLICY_VERSION


BUNDLE_MEDIA_TYPE = "application/x-rmc-sync-bundle+ndjson"
BUNDLE_VERSION = 1


def _signing_key() -> bytes:
    secret = (
        getattr(settings, "RMC_SYNC_BUNDLE_SIGNING_KEY", None)
        or getattr(settings, "SECRET_KEY", "")
        or ""
    )
    return str(secret).encode("utf-8")


def export_delta_bundle(*, school_id: int, rows: list[dict[str, Any]], device_id: str = "") -> bytes:
    """Serialize rows to signed NDJSON bundle bytes."""
    header = {
        "bundle_version": BUNDLE_VERSION,
        "school_id": school_id,
        "device_id": (device_id or "")[:128],
        "exported_at": int(time.time()),
        "row_count": len(rows),
        "policy_version": POLICY_VERSION,
    }
    body_lines = [json.dumps(header, separators=(",", ":"), sort_keys=True)]
    for row in rows:
        body_lines.append(
            json.dumps(row, separators=(",", ":"), sort_keys=True, default=str)
        )
    payload = "\n".join(body_lines).encode("utf-8")
    sig = hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()
    trailer = json.dumps({"signature": sig}, separators=(",", ":"))
    return payload + b"\n" + trailer.encode("utf-8") + b"\n"


def iter_bundle_lines(data: bytes) -> Iterator[dict[str, Any]]:
    for line in data.decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def verify_and_parse_bundle(data: bytes, *, expected_school_id: int | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Verify HMAC trailer and return (rows, errors)."""
    errors: list[str] = []
    raw_lines = [ln for ln in data.decode("utf-8").splitlines() if ln.strip()]
    if len(raw_lines) < 2:
        return [], ["bundle_too_short"]
    try:
        trailer = json.loads(raw_lines[-1])
    except json.JSONDecodeError:
        return [], ["invalid_signature_line"]
    if "signature" not in trailer:
        return [], ["missing_signature"]
    payload_text = "\n".join(raw_lines[:-1]).encode("utf-8")
    expected_sig = trailer["signature"]
    actual_sig = hmac.new(_signing_key(), payload_text, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, actual_sig):
        return [], ["signature_mismatch"]
    try:
        parsed = [json.loads(ln) for ln in raw_lines[:-1]]
    except json.JSONDecodeError:
        return [], ["invalid_bundle_json"]
    header = parsed[0]
    if int(header.get("bundle_version") or 0) != BUNDLE_VERSION:
        return [], ["unsupported_bundle_version"]
    if expected_school_id is not None and int(header.get("school_id") or 0) != int(expected_school_id):
        return [], ["school_mismatch"]
    rows = parsed[1:]
    try:
        declared_count = int(header["row_count"])
    except (KeyError, TypeError, ValueError):
        return [], ["invalid_row_count"]
    if declared_count != len(rows):
        return [], ["row_count_mismatch"]
    return rows, errors


__all__ = [
    "BUNDLE_MEDIA_TYPE",
    "BUNDLE_VERSION",
    "export_delta_bundle",
    "verify_and_parse_bundle",
]
