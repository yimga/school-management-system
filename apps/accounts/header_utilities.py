"""Quiet-header v2 context: finance-primary roles and live sync urgency."""
from __future__ import annotations

from django.core.cache import cache
from django.db import DatabaseError, connection, transaction

from apps.accounts.models import User

_SYNC_CACHE_TTL_SECONDS = 60
_HEADER_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    RuntimeError,
    TypeError,
    ValueError,
)
_FINANCE_PRIMARY_ROLES = frozenset(
    {
        User.Role.BURSAR.value,
        User.Role.FINANCE_STAFF.value,
        User.Role.ACCOUNTANT.value,
    }
)


def _reset_db_state() -> None:
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        elif connection.needs_rollback:
            connection.rollback()
    except (DatabaseError, RuntimeError):
        pass


def is_finance_primary_role(role: object) -> bool:
    token = str(getattr(role, "value", role) or "").strip().upper()
    return token in _FINANCE_PRIMARY_ROLES


def _sync_context_for_school(school) -> dict:
    payload = {
        "quiet_header_sync_at": None,
        "quiet_header_sync_ok": False,
        "quiet_header_sync_conflicts": 0,
    }
    if school is None:
        return payload
    cache_key = f"rmc.quiet-header.sync.{getattr(school, 'pk', '')}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    try:
        from apps.sync_engine.models import EdgeSyncRun

        # tenant-isolation-allow: explicit-school-row-on-edge-sync-run-for-header-status
        run = EdgeSyncRun.objects.filter(school=school).first()
        if run is not None:
            payload["quiet_header_sync_at"] = run.finished_at or run.created_at
            payload["quiet_header_sync_ok"] = bool(run.ok)
            payload["quiet_header_sync_conflicts"] = int(run.conflicts or 0)
    except DatabaseError:
        _reset_db_state()
    except _HEADER_SOFT_FAILURES:
        pass
    cache.set(cache_key, payload, _SYNC_CACHE_TTL_SECONDS)
    return payload


def attach_quiet_header_context(request, ctx: dict, school=None) -> dict:
    """Merge quiet-header flags into an existing request context dict."""
    role = ctx.get("EFFECTIVE_PORTAL_ROLE") or getattr(
        getattr(request, "user", None), "role", ""
    )
    ctx["QUIET_HEADER_FINANCE_PRIMARY"] = is_finance_primary_role(role)
    if school is None:
        school = getattr(request, "school", None)
    ctx.update(_sync_context_for_school(school))
    return ctx
