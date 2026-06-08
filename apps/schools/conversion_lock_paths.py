"""
Explicit path prefixes allowed while conversion lock is active.

Completion is driven by ``conversion_lock_state`` / model signals, not URL guessing.
This module only enumerates which routes stay reachable before ``first_action_completed``.
"""

from __future__ import annotations

# Auth, onboarding, asset delivery (non-strict / legacy).
CONVERSION_LOCK_BASE_PREFIXES: tuple[str, ...] = (
    "/authentication/",
    "/activation/",
    "/static/",
    "/media/",
)

# Strict mode: never use a blanket "/authentication/" prefix — only these paths stay open
# so login/logout/MFA/SSO still work while profiles, messages, backend, RBAC stay unreachable.
CONVERSION_LOCK_AUTH_PREFIXES_STRICT: tuple[str, ...] = (
    "/authentication/login/",
    "/authentication/logout/",
    "/authentication/redirect/",
    "/authentication/school-picker/",
    "/authentication/switch-portal-role/",
    "/authentication/mfa/",
    "/authentication/end-impersonation/",
    "/authentication/impersonate/",
    "/authentication/claim-invite/",
    # First-run owner onboarding (set password + name → school → done). A brand-
    # new owner hasn't completed "first action" yet, so without this the lock
    # would eject them OUT of the very wizard that sets their password, into
    # /activation/first-action/ (login+MFA wall). Token-authed, so safe to allow.
    "/authentication/onboarding/",
    "/authentication/oidc/",
    "/authentication/saml/",
)

# Strict base paths without authentication (activation + assets).
CONVERSION_LOCK_BASE_PREFIXES_STRICT: tuple[str, ...] = (
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
# Finance: exclude ``/finance/`` root dashboard — allow operational payment/invoice paths only.
# Reports: exclude blanket ``/reports/`` — allow publish/export/report-card workflow URLs only.
CONVERSION_LOCK_WORKFLOW_PREFIXES_NARROW: tuple[str, ...] = (
    "/portal/attendance/",
    "/portal/parent/attendance-discipline",
    "/portal/teacher/attendance",
    "/evals/teacher/marks/",
    "/evals/teacher/marks/entry",
    "/reports/parent/",
    "/reports/share/",
    "/reports/verify-hash/",
    "/reports/publish/",
    "/reports/statistical-return/",
    "/reports/promotion-preview/",
    "/reports/regulatory-export/",
    "/finance/invoices/",
    "/finance/payments/",
    "/finance/access/",
    "/finance/fees/",
    "/finance/trial-balance/",
    "/finance/reports/",
    "/finance/notifications/",
    "/finance/requests/",
    "/finance/reconciliation/",
    "/finance/accounting/",
    "/portal/api/offline/",
    "/kb/",
    "/siteconfig/reports/",
    "/demo/flow/",
)


# Explicit deny (documentation / defense-in-depth when strict auth uses narrow prefixes).
_CONVERSION_LOCK_BLOCKED_WHEN_STRICT: tuple[str, ...] = (
    "/authentication/backend/",
    "/authentication/rbac/",
)


def _matches_health(path: str) -> bool:
    p = path or ""
    pl = p.lower()
    if pl == "/health" or pl.startswith("/health/"):
        return True
    # Tenant observability probe (see config.tenant_urls api_health).
    if pl.startswith("/api/health"):
        return True
    # Ops probes (same policy bucket as health).
    if pl.startswith("/healthz") or pl.startswith("/ready") or pl.startswith("/status"):
        return True
    return False


def _matches_strict_authentication_allowlist(path: str) -> bool:
    """Exact ``/authentication/`` root redirect + SSO/MFA/login prefixes only."""
    p = (path or "").replace("\\", "/").lower()
    if not p.startswith("/"):
        p = "/" + p
    if p.rstrip("/") == "/authentication":
        return True
    for prefix in CONVERSION_LOCK_AUTH_PREFIXES_STRICT:
        if p.startswith(prefix.lower()):
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
    strict = getattr(settings, "CONVERSION_LOCK_STRICT", False)
    if strict:
        for blocked in _CONVERSION_LOCK_BLOCKED_WHEN_STRICT:
            if p.startswith(blocked.lower()):
                return False
    if p.startswith("/favicon"):
        return True
    if _matches_health(p):
        return True
    if strict:
        if _matches_strict_authentication_allowlist(p):
            return True
        for prefix in (
            *CONVERSION_LOCK_BASE_PREFIXES_STRICT,
            *_workflow_prefixes(),
            *extra_prefixes,
        ):
            if p.startswith(prefix.lower()):
                return True
        return False
    for prefix in (
        *CONVERSION_LOCK_BASE_PREFIXES,
        *_workflow_prefixes(),
        *extra_prefixes,
    ):
        if p.startswith(prefix):
            return True
    return False
