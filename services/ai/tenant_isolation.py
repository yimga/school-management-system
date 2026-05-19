"""
Multi-tenant scope enforcement before RAG retrieval or model calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PlatformTier(str, Enum):
    PLATFORM_MANAGER = "platform_manager"
    SCHOOL_TENANT = "school_tenant"


class SecurityIsolationException(Exception):
    """Raised when a lookup would cross tenant boundaries."""


@dataclass(frozen=True)
class TenantScope:
    tier: PlatformTier
    tenant_id: str | None
    school: Any | None
    user_id: str | None
    role: str | None
    is_staff: bool
    is_superuser: bool


class TenantContextEnforcer:
    """Binds AI retrieval and prompts to platform vs school tenant scopes."""

    def __init__(self, user: Any, *, school: Any | None = None) -> None:
        self.user = user
        self.school = school

    def _control_plane_operator(self) -> bool:
        try:
            from apps.schools.control_plane import user_has_control_plane_access

            return user_has_control_plane_access(self.user)
        except ImportError:
            return False

    def resolve_scope(self) -> TenantScope:
        user = self.user
        school = self.school
        uid = getattr(user, "pk", None) or getattr(user, "id", None)
        role = (
            getattr(user, "role", None)
            or getattr(user, "portal_role", None)
            or getattr(user, "user_type", None)
        )
        is_staff = bool(getattr(user, "is_staff", False))
        is_superuser = bool(getattr(user, "is_superuser", False))
        school_id = None
        if school is not None:
            school_id = str(getattr(school, "pk", None) or getattr(school, "id", None) or "")

        if is_superuser or (is_staff and school is None) or self._control_plane_operator():
            if school is None and (is_superuser or self._control_plane_operator()):
                return TenantScope(
                    tier=PlatformTier.PLATFORM_MANAGER,
                    tenant_id=None,
                    school=None,
                    user_id=str(uid) if uid is not None else None,
                    role=str(role) if role else None,
                    is_staff=is_staff,
                    is_superuser=is_superuser,
                )

        if school_id:
            return TenantScope(
                tier=PlatformTier.SCHOOL_TENANT,
                tenant_id=school_id,
                school=school,
                user_id=str(uid) if uid is not None else None,
                role=str(role) if role else None,
                is_staff=is_staff,
                is_superuser=is_superuser,
            )

        return TenantScope(
            tier=PlatformTier.SCHOOL_TENANT,
            tenant_id=None,
            school=None,
            user_id=str(uid) if uid is not None else None,
            role=str(role) if role else None,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )

    def assert_retrieval_allowed(
        self,
        *,
        row_school_id: str | None,
        global_row: bool = False,
    ) -> None:
        scope = self.resolve_scope()
        if scope.tier == PlatformTier.PLATFORM_MANAGER:
            return
        if global_row and row_school_id is None:
            return
        if scope.tenant_id is None:
            raise SecurityIsolationException("tenant context required for school-scoped retrieval")
        if row_school_id is not None and str(row_school_id) != str(scope.tenant_id):
            raise SecurityIsolationException("cross-tenant retrieval blocked")

    def build_context_header(
        self,
        *,
        active_url: str,
        permission_labels: list[str],
    ) -> str:
        scope = self.resolve_scope()
        tier_label = (
            "Platform Management Tier (Super-Admin)"
            if scope.tier == PlatformTier.PLATFORM_MANAGER
            else "School Tenant Tier (Local School Staff)"
        )
        perms = ", ".join(permission_labels) if permission_labels else "none_declared"
        return (
            "[USER CURRENT CONTEXT]\n"
            f"User Role: {scope.role or 'unknown'}\n"
            f"Platform Tier: {tier_label}\n"
            f"Active Screen: {active_url or '/'}\n"
            f"User Permissions: {perms}\n"
        )
