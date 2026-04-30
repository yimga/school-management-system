"""
Explicit path prefixes allowed while conversion lock is active.

Completion is driven by ``conversion_lock_state`` / model signals, not URL guessing.
This module only enumerates which routes stay reachable before ``first_action_completed``.
"""

from __future__ import annotations

# Auth, onboarding, asset delivery.
CONVERSION_LOCK_BASE_PREFIXES: tuple[str, ...] = (
    "/authentication/",
    "/activation/",
    "/static/",
    "/media/",
)

# Broad allowlist (legacy / non-strict): full portal for workflow POSTs.
CONVERSION_LOCK_WORKFLOW_PREFIXES: tuple[str, ...] = (
    "/portal/",
    "/evals/",
    "/reports/",
    "/finance/",
)

# Strict: only first-value surfaces (not dashboard home routes).
CONVERSION_LOCK_WORKFLOW_PREFIXES_NARROW: tuple[str, ...] = (
    "/portal/attendance/",
    "/portal/parent/attendance-discipline",
    "/portal/teacher/attendance",
    "/evals/teacher/marks/",
    "/evals/teacher/marks/entry",
    "/reports/",
    "/finance/",
    "/portal/api/offline/",
    "/kb/",
    "/siteconfig/reports/",
    "/demo/flow/",
)


# When CONVERSION_LOCK_STRICT is on, the broad "/authentication/" prefix is too permissive
# (it would allow the full operator backend). Block dashboard-style paths explicitly.
_CONVERSION_LOCK_BLOCKED_WHEN_STRICT: tuple[str, ...] = (
    "/authentication/backend/",
    "/authentication/rbac/",
)


def _matches_health(path: str) -> bool:
    p = path or ""
    if p == "/health" or p.startswith("/health/"):
        return True
    # Ops probes (same policy bucket as health).
    if p.startswith("/healthz") or p.startswith("/ready") or p.startswith("/status"):
        return True
    return False


def _workflow_prefixes() -> tuple[str, ...]:
    from django.conf import settings

    if getattr(settings, "CONVERSION_LOCK_USE_NARROW_WORKFLOW_PATHS", False):
        return CONVERSION_LOCK_WORKFLOW_PREFIXES_NARROW
    return CONVERSION_LOCK_WORKFLOW_PREFIXES


def path_matches_conversion_allowlist(path: str, extra_prefixes: tuple[str, ...]) -> bool:
    from django.conf import settings

    p = (path or "").replace("\\", "/").lower()
    if not p.startswith("/"):
        p = "/" + p
    if getattr(settings, "CONVERSION_LOCK_STRICT", False):
        for blocked in _CONVERSION_LOCK_BLOCKED_WHEN_STRICT:
            if p.startswith(blocked.lower()):
                return False
    if p.startswith("/favicon"):
        return True
    if _matches_health(p):
        return True
    for prefix in (
        *CONVERSION_LOCK_BASE_PREFIXES,
        *_workflow_prefixes(),
        *extra_prefixes,
    ):
        if p.startswith(prefix):
            return True
    return False
