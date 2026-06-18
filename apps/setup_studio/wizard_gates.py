"""Wizard gate checks — permissions + prerequisite completion (OSS-only runtime deps)."""

from __future__ import annotations

from typing import Any

from apps.setup_studio import wizard_engine, wizard_state_resolver
from apps.setup_studio.wizard_engine import GateBlockedError, WizardDefinition

# Canonical tenant-admin User.Role tokens (mirrors wizard_views._TENANT_ADMIN_USER_ROLES).
_TENANT_ADMIN_USER_ROLES = frozenset({"ADMIN", "PROPRIETOR", "PRINCIPAL"})  # role-string-allow: canonical-User.Role-tenant-admin-tokens


def _request_is_tenant_admin(request: Any) -> bool:
    """True when the request user is a tenant owner/admin (not merely staff on manager host)."""
    if request is None:
        return False
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False):
        return True
    for role_attr in ("user_role", "role", "primary_role"):
        role = getattr(user, role_attr, None)
        if role and str(role).strip().upper() in _TENANT_ADMIN_USER_ROLES:
            return True
    return False


def prerequisite_satisfied(*, school: Any, prerequisite_key: str) -> bool:
    if not prerequisite_key:
        return True
    if wizard_state_resolver.is_wizard_completed(school, prerequisite_key):
        return True
    if prerequisite_key == "multi_campus_local_sovereignty":
        from apps.setup_studio.sovereignty_kernel import sovereignty_kernel_ready

        return sovereignty_kernel_ready(school)
    return False


def assert_wizard_gates(
    *,
    wizard: WizardDefinition,
    school: Any,
    request: Any,
) -> None:
    """Raise ``GateBlockedError`` when gates block the wizard for this tenant."""
    gates = wizard.gates or {}
    prereq = gates.get("prerequisite_wizard")
    if prereq and not prerequisite_satisfied(school=school, prerequisite_key=str(prereq)):
        raise GateBlockedError(f"prerequisite_not_met:{prereq}")

    perm = gates.get("permission_codename")
    if perm and request is not None:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            tenant_admin_entitled = (
                _request_is_tenant_admin(request)
                and "tenant_admin" in (wizard.audience or ())
            )
            if not tenant_admin_entitled:
                if not getattr(user, "is_superuser", False) and not user.has_perm(str(perm)):
                    if not getattr(user, "is_staff", False):
                        raise GateBlockedError(f"permission_denied:{perm}")
