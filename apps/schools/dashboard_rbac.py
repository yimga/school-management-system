# -*- coding: utf-8 -*-
"""
Dual-dashboard topology RBAC — operational vs configuration surfaces.

Platform (manager host):
  - platform_super: /super/ — real-time operator command center
  - platform_config: /configuration/, /admin/, /internal-admin/

Tenant (school host):
  - tenant_super: /authentication/backend/, role portals — daily campus operations
  - tenant_config: /admin/, /siteconfig/ (mutations), deep settings engines

See docs/CONTROL_PLANE_BOUNDARY_RULES.md and docs/CONTROL_PLANE_AND_PLATFORM_ADMIN.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from django.http import HttpRequest

logger = logging.getLogger(__name__)

DashboardTier = Literal[
    "platform_super",
    "platform_config",
    "tenant_super",
    "tenant_config",
    "public",
    "unknown",
]

# Roles allowed to open tenant configuration / Django admin (grading, fees, OAuth, etc.).
TENANT_CONFIG_ROLE_CODES = frozenset(
    {
        "SUPERADMIN",
        "ADMIN",
        "IT_ADMIN",
        "LEADERSHIP",
        "PROPRIETOR",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "BURSAR",
    }
)

# Daily operational roles — must not mutate configuration-tier routes.
TENANT_OPERATIONAL_ROLE_CODES = frozenset(
    {
        "TEACHER",
        "PARENT",
        "STUDENT",
        "SECRETARY",
        "DEAN",
        "HOD",
        "DEPT_LEAD",
        "CENSOR",
        "DISCIPLINE_MASTER",
        "BOARDING_MANAGER",
        "FINANCE_STAFF",
        "ACADEMICS_STAFF",
        "COMMS_STAFF",
        "ACCOUNTANT",
    }
)

PLATFORM_CONFIG_PREFIXES = (
    "/configuration/",
    "/admin/",
    "/internal-admin/",
)

PLATFORM_SUPER_PREFIXES = ("/super/",)

TENANT_CONFIG_PREFIXES = (
    "/admin/",
)

# Siteconfig paths that change system state (not personal prefs / tours).
TENANT_CONFIG_SITE_PREFIXES = (
    "/siteconfig/console",
    "/siteconfig/dashboard",
    "/siteconfig/grading",
    "/siteconfig/region",
    "/siteconfig/feature",
    "/siteconfig/theme",
    "/siteconfig/billing",
    "/siteconfig/metadata",
    "/siteconfig/tag-manager",
    "/siteconfig/zero-ticket",
    "/siteconfig/permission",
    "/siteconfig/academic",
    "/siteconfig/departments",
    "/siteconfig/report",
    "/siteconfig/bulk",
    "/siteconfig/import",
    "/siteconfig/export",
    "/siteconfig/runtime",
    "/siteconfig/control",
)

TENANT_CONFIG_SITE_BYPASS_PREFIXES = (
    "/siteconfig/preferences",
    "/siteconfig/api/tour-",
)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class DashboardAccessDecision:
    allowed: bool
    tier: DashboardTier
    reason: str = ""
    redirect_hint: str = ""


def _normalize_path(path: str) -> str:
    return (path or "").strip() or "/"


def classify_dashboard_tier(request: HttpRequest) -> DashboardTier:
    """Classify the request path into a dashboard topology tier."""
    path = _normalize_path(getattr(request, "path", "") or "")
    host_kind = (getattr(request, "public_host_kind", None) or "").lower()

    if host_kind == "manager" or path.startswith("/super/"):
        if any(path.startswith(p) for p in PLATFORM_CONFIG_PREFIXES):
            return "platform_config"
        if any(path.startswith(p) for p in PLATFORM_SUPER_PREFIXES):
            return "platform_super"
        return "unknown"

    if host_kind == "tenant" or getattr(request, "school", None) is not None:
        if any(path.startswith(p) for p in TENANT_CONFIG_PREFIXES):
            return "tenant_config"
        if path.startswith("/siteconfig/"):
            if any(path.startswith(p) for p in TENANT_CONFIG_SITE_BYPASS_PREFIXES):
                return "tenant_super"
            if any(path.startswith(p) for p in TENANT_CONFIG_SITE_PREFIXES):
                return "tenant_config"
        if path.startswith("/authentication/backend/") or path.startswith("/portal/"):
            return "tenant_super"
        return "unknown"

    return "public"


def _user_role_code(request: HttpRequest) -> str:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    role = getattr(user, "role", None)
    if hasattr(role, "value"):
        return str(role.value or "").upper()
    return str(role or "").upper()


def user_may_access_tenant_config(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = _user_role_code(request)
    if role in TENANT_CONFIG_ROLE_CODES:
        return True
    if hasattr(user, "has_feature_permission") and user.has_feature_permission(
        "settings.manage"
    ):
        return True
    return False


def evaluate_dashboard_topology_access(request: HttpRequest) -> DashboardAccessDecision:
    """
    Return whether the authenticated user may access the classified dashboard tier.
    Unauthenticated callers are allowed through (login/MFA layers handle them).
    """
    tier = classify_dashboard_tier(request)
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return DashboardAccessDecision(allowed=True, tier=tier)

    method = (getattr(request, "method", None) or "GET").upper()
    role = _user_role_code(request)
    host_kind = (getattr(request, "public_host_kind", None) or "").lower()

    # Manager host: tenant staff already denied by ManagerHostControlPlaneRequiredMiddleware.
    if host_kind == "manager" and tier == "platform_config":
        try:
            from apps.schools.control_plane import user_has_control_plane_access

            if user_has_control_plane_access(user):
                return DashboardAccessDecision(allowed=True, tier=tier)
        except ImportError:
            pass
        if getattr(user, "is_superuser", False):
            return DashboardAccessDecision(allowed=True, tier=tier)
        return DashboardAccessDecision(
            allowed=False,
            tier=tier,
            reason="platform_config_requires_control_plane",
            redirect_hint="/super/",
        )

    if tier == "tenant_config":
        if method in SAFE_METHODS and _normalize_path(request.path).startswith(
            "/portal/configure"
        ):
            # Settings hub catalog is read-only discovery for all authenticated roles.
            return DashboardAccessDecision(allowed=True, tier=tier)
        if user_may_access_tenant_config(request):
            return DashboardAccessDecision(allowed=True, tier=tier)
        return DashboardAccessDecision(
            allowed=False,
            tier=tier,
            reason="tenant_config_role_denied",
            redirect_hint="/authentication/backend/",
        )

    if tier == "tenant_super" and role in TENANT_OPERATIONAL_ROLE_CODES:
        return DashboardAccessDecision(allowed=True, tier=tier)

    return DashboardAccessDecision(allowed=True, tier=tier)


def log_topology_violation(request: HttpRequest, decision: DashboardAccessDecision) -> None:
    """Security trace for cross-tier access attempts (no PII)."""
    try:
        from apps.observability.tracing import set_tags, start_named_transaction

        txn = start_named_transaction(
            "dashboard.topology.denied",
            op="security",
        )
        set_tags(
            dashboard_tier=decision.tier,
            dashboard_reason=decision.reason or "denied",
            http_method=getattr(request, "method", ""),
        )
        if txn is not None:
            from apps.observability.tracing import finish_transaction

            finish_transaction(txn)
    except ImportError:
        pass

    logger.warning(
        "dashboard_topology_denied tier=%s reason=%s path=%s role=%s",
        decision.tier,
        decision.reason,
        getattr(request, "path", ""),
        _user_role_code(request),
        extra={
            "dashboard_tier": decision.tier,
            "dashboard_reason": decision.reason,
        },
    )
