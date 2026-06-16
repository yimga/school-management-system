"""HMAC-signed deletion certificate for a tenant purge (owner-decision b).

Mirrors the platform's audit-root-signing approach (canonical JSON ->
HMAC-SHA512, constant-time verify) but for a purge certificate. Self-contained
key resolution via ``TENANT_PURGE_CERT_SIGNING_KEY`` (falls back to SECRET_KEY)
so it works in dev; a production deploy sets the dedicated env var. The
certificate is a portable, verifiable proof that a specific tenant's data was
purged — it survives the School row because PurgeOperation does.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from django.conf import settings


def _signing_key() -> bytes:
    raw = getattr(settings, "TENANT_PURGE_CERT_SIGNING_KEY", "") or getattr(
        settings, "SECRET_KEY", ""
    )
    return raw.encode("utf-8") if isinstance(raw, str) else bytes(raw or b"")


def _canonical(payload: dict) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def build_certificate_payload(op) -> dict:
    """Deterministic, PII-free certificate body for a completed purge."""
    return {
        "purge_operation_id": str(op.id),
        "school_id": op.school_id,
        "school_slug": op.school_slug,
        "row_total": int(op.row_total or 0),
        "schema_dropped": bool(op.schema_dropped),
        "sessions_revoked": int(op.sessions_revoked or 0),
        "completed_phases": list(op.completed_phases or []),
        "completed_at": op.completed_at.isoformat() if op.completed_at else None,
    }


def sign_deletion_certificate(payload: dict) -> str:
    """Return the 128-char hex HMAC-SHA512 signature over the canonical payload."""
    return hmac.new(_signing_key(), _canonical(payload), hashlib.sha512).hexdigest()


def verify_deletion_certificate(payload: dict, signature: str) -> bool:
    """Constant-time verify a certificate payload against its signature."""
    if not signature:
        return False
    expected = sign_deletion_certificate(payload)
    return hmac.compare_digest(expected, signature)
