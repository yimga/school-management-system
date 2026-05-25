"""Signed read-only IAM snapshots for offline navigation (batch 1507)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.accounts.rebac import flatten_capabilities, snapshot_integrity_hash, tuples_for_user

SNAPSHOT_VERSION = 1


def _signing_key() -> bytes:
    secret = (
        getattr(settings, "RMC_IAM_SNAPSHOT_SIGNING_KEY", None)
        or getattr(settings, "SECRET_KEY", "")
        or ""
    )
    return str(secret).encode("utf-8")


def snapshot_ttl_hours(*, offline_token: bool = False) -> int:
    if offline_token:
        return int(getattr(settings, "RMC_IAM_SNAPSHOT_OFFLINE_TOKEN_TTL_HOURS", 12))
    return int(getattr(settings, "RMC_IAM_SNAPSHOT_TTL_HOURS", 168))


def build_permission_snapshot(
    user,
    *,
    school,
    offline_token: bool = False,
    device_id: str = "",
) -> dict[str, Any]:
    """Canonical snapshot payload (before signature wrapper)."""
    now = timezone.now()
    expires = now + timedelta(hours=snapshot_ttl_hours(offline_token=offline_token))
    capabilities = flatten_capabilities(user, school=school)
    relations = tuples_for_user(school=school, user=user)
    body = {
        "snapshot_version": SNAPSHOT_VERSION,
        "school_id": str(school.pk),
        "user_id": str(user.pk),
        "device_id": (device_id or "")[:128],
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "capabilities": capabilities,
        "relations": relations,
        "read_only": True,
        "offline_admin_grants": False,
    }
    body["integrity_hash"] = snapshot_integrity_hash(
        {k: v for k, v in body.items() if k != "integrity_hash"},
    )
    return body


def sign_snapshot(body: dict[str, Any]) -> dict[str, Any]:
    """Return body + HMAC signature for client verification."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    sig = hmac.new(_signing_key(), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**body, "signature": sig}


def verify_snapshot_signature(body: dict[str, Any]) -> bool:
    sig = body.pop("signature", None)
    if not sig:
        return False
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    expected = hmac.new(_signing_key(), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def snapshot_not_expired(body: dict[str, Any]) -> bool:
    raw = body.get("expires_at") or ""
    if not raw:
        return False
    try:
        from django.utils.dateparse import parse_datetime

        exp = parse_datetime(raw)
        if exp is None:
            return False
        if timezone.is_naive(exp):
            exp = timezone.make_aware(exp)
        return exp > timezone.now()
    except (TypeError, ValueError):
        return False


def offline_capability_bitmap(user, *, school) -> list[str]:
    """Bitmap for OfflineCapabilityToken — from snapshot capabilities."""
    snap = build_permission_snapshot(user, school=school, offline_token=True)
    caps = list(snap.get("capabilities") or [])
    if not caps:
        caps = ["attendance.mark", "grade.submit"]
    return sorted(set(caps))[:64]
