"""Signed NDJSON delta bundles for LAN data-mule sync (SODP batch 1412)."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
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


def export_delta_bundle(*, school_id: str | int, rows: list[dict[str, Any]], device_id: str = "") -> bytes:
    """Serialize rows to signed NDJSON bundle bytes."""
    header = {
        "bundle_version": BUNDLE_VERSION,
        # str() so UUID school ids (the platform's School.pk type) both JSON-serialize
        # here and compare cleanly on the verify side. Backwards compatible with int ids.
        "school_id": str(school_id),
        "device_id": (device_id or "")[:128],
        "exported_at": int(time.time()),
        "row_count": len(rows),
        "policy_version": POLICY_VERSION,
        # Replay defence. The nonce is INSIDE the signed payload, so it cannot be
        # rewritten to disguise a captured bundle as a new one. A signature alone proves
        # who built a bundle, never that this is the first time you have been handed it -
        # see sync_engine.models.SyncBundleReceipt. It is regenerated per BUILD, so a
        # legitimate retry after a network timeout rebuilds with a fresh nonce and is
        # accepted (and applied idempotently), while replaying the captured bytes is not.
        "nonce": secrets.token_hex(16),
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


def bundle_nonce(data: bytes) -> str:
    """The replay nonce out of a bundle this side BUILT.

    Deliberately unverified, and safe precisely because of who calls it: the box reads
    the header of bytes it just produced itself, to remember which bundle it put on the
    wire. Nothing trusts this value as evidence about a bundle that arrived from
    somewhere else -- the receiving side gets its nonce from
    ``verify_and_parse_bundle(collect=...)``, which only populates the header AFTER the
    signature checks out.

    Returns "" for anything unparseable rather than raising: the caller is recording a
    breadcrumb after a push already failed, and a bookkeeping error must not turn a
    recoverable timeout into a crash.
    """
    try:
        for line in data.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            header = json.loads(line)
            return str(header.get("nonce") or "") if isinstance(header, dict) else ""
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return ""
    return ""


def iter_bundle_lines(data: bytes) -> Iterator[dict[str, Any]]:
    for line in data.decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def verify_and_parse_bundle(
    data: bytes,
    *,
    expected_school_id: str | int | None = None,
    collect: dict | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Verify HMAC trailer and return (rows, errors).

    Pass ``collect=`` a mutable dict to also receive the verified ``header`` and the
    ``payload_digest``. Kept out of the return tuple so every existing 2-tuple caller is
    untouched. The header is only ever placed there AFTER the signature checks out, so a
    caller cannot accidentally trust an unverified nonce.
    """
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
    if expected_school_id is not None and str(header.get("school_id") or "") != str(expected_school_id):
        return [], ["school_mismatch"]
    rows = parsed[1:]
    try:
        declared_count = int(header["row_count"])
    except (KeyError, TypeError, ValueError):
        return [], ["invalid_row_count"]
    if declared_count != len(rows):
        return [], ["row_count_mismatch"]
    if collect is not None:
        collect["header"] = header
        collect["payload_digest"] = hashlib.sha256(payload_text).hexdigest()
    return rows, errors


__all__ = [
    "BUNDLE_MEDIA_TYPE",
    "BUNDLE_VERSION",
    "export_delta_bundle",
    "verify_and_parse_bundle",
]
