"""Env-driven policy for tenant offboarding (no hardcoded grace periods)."""

from __future__ import annotations

import os
from datetime import date, timedelta


def _env_bool(name: str, default: str = "0") -> bool:
    try:
        from django.conf import settings

        if hasattr(settings, name):
            raw = getattr(settings, name)
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in ("1", "true", "yes")
    except Exception:
        pass
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def self_service_enabled() -> bool:
    return _env_bool("TENANT_SELF_SERVICE_OFFBOARDING_ENABLED", "1")


def auto_purge_enabled() -> bool:
    return _env_bool("TENANT_AUTO_PURGE_ENABLED", "0")


def auto_purge_grace_days() -> int:
    raw = os.environ.get("TENANT_AUTO_PURGE_GRACE_DAYS", "30").strip()
    try:
        days = int(raw)
    except ValueError:
        days = 30
    return max(7, min(days, 365))


def dual_approval_required() -> bool:
    return _env_bool("TENANT_PURGE_REQUIRE_DUAL_APPROVAL", "0")


def s3_cleanup_enabled() -> bool:
    return _env_bool("TENANT_OFFBOARDING_S3_CLEANUP_ENABLED", "1")


def offboarding_email_enabled() -> bool:
    return _env_bool("TENANT_OFFBOARDING_EMAIL_ENABLED", "1")


def notify_tenant_admins_on_closure() -> bool:
    return _env_bool("TENANT_OFFBOARDING_NOTIFY_TENANT_ADMINS", "1")


def default_scheduled_purge_date(*, from_day: date | None = None) -> date:
    base = from_day or date.today()
    return base + timedelta(days=auto_purge_grace_days())


def tenant_media_prefixes(school_slug: str, school_id: str) -> list[str]:
    """S3/local key prefixes for a tenant's uploaded objects."""
    sid = str(school_id)
    return [
        f"tenants/{school_slug}/",
        f"tenants/{sid}/",
        f"tenant_archives/{school_slug}/",
    ]
