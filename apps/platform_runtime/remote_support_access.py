"""Access helpers for the Remote Support module.

Two distinct helpers, two distinct threat models (the owner asked for BOTH):

- ``operator_can_remote_support`` — a PLATFORM operator (cross-tenant staff)
  running a remote-support session for a tenant. Gated by the
  ``platform.tenant_support.remote`` scope AND scoped to the specific tenant via
  the same superuser / OperatorTenantAssignment / JIT authorization the
  impersonation gate uses. Remote support does NOT require impersonation — the
  ``tenant_support`` tier can assist without act-as.

- ``user_can_provide_school_support`` — an IN-SCHOOL support person (the school's
  own IT/admin helper) for THEIR school only. Granted via the existing AccessRole
  / feature-permission system (the ``school_support.assist`` permission), NOT a
  new hardcoded ``User.Role`` (which would trip ``scan_role_strings`` and need
  wiring at 100+ sites). No control-plane access.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TENANT_SUPPORT,
    user_has_platform_scope,
)

logger = logging.getLogger(__name__)

# In-school elevated-support capability code (attach to an AccessRole / grant as
# a feature permission). Lives in the tenant RBAC namespace, not platform scopes.
SCHOOL_SUPPORT_ASSIST_PERMISSION = "school_support.assist"

_TENANT_LOOKUP_ERRORS = (ImportError, OSError, RuntimeError, TypeError, ValueError)


def operator_is_authorized_for_tenant(user, school) -> bool:
    """Tenant-scoping check shared by impersonation and remote support.

    True when the actor is a superuser, holds an active OperatorTenantAssignment
    for the school, or holds an active JIT grant. This answers "is this operator
    authorized for THIS tenant at all" — independent of which capability
    (impersonate vs remote-support) they are exercising.
    """
    if getattr(user, "is_superuser", False):
        return True
    try:
        from apps.platform_runtime.models import OperatorTenantAssignment

        if OperatorTenantAssignment.has_active(user, school):
            return True
    except _TENANT_LOOKUP_ERRORS:
        pass
    try:
        from apps.platform_runtime.jit_operator_controller import (
            check_jit_authorization,
        )

        grant = check_jit_authorization(
            operator_user_id=getattr(user, "id", None),
            school_settings=getattr(school, "settings", None),
        )
        if grant.granted:
            return True
    except _TENANT_LOOKUP_ERRORS:
        pass
    return False


def operator_can_remote_support(user, school) -> bool:
    """A platform operator may run a remote-support session for this tenant."""
    if not getattr(user, "is_authenticated", False):
        return False
    if not user_has_platform_scope(user, PLATFORM_SCOPE_TENANT_SUPPORT):
        return False
    return operator_is_authorized_for_tenant(user, school)


def user_can_provide_school_support(user, school) -> bool:
    """An in-school support person may assist users within THEIR school.

    True for a school admin (superuser/is_staff/role==ADMIN) or any user holding
    the ``school_support.assist`` feature-permission in this school. Reuses the
    existing RBAC; never grants control-plane access.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    _User = get_user_model()
    role = getattr(user, "role", None)
    if (
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or (role is not None and role == _User.Role.ADMIN)
    ):
        return True
    check = getattr(user, "has_feature_permission", None)
    if callable(check):
        try:
            return bool(check(SCHOOL_SUPPORT_ASSIST_PERMISSION, school=school))
        except (TypeError, ValueError, AttributeError):
            return False
    return False
