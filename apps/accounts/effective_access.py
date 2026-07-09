"""Canonical effective-access facade (sovereign consolidation, 2026-07-02).

THE single consumer entry point for object/module access decisions. The
platform's authorization intent converges here: each function delegates
verbatim to the battle-tested helper that owns the rule (so behavior is
bit-identical to the pre-facade call-sites). The PDP was promoted past
advisory on 2026-07-09: ``POLICY_PDP_ENFORCEMENT_MODE`` defaults to
``enforce`` and the IAM surfaces enforce via parity probes built on this
module's ``permission_access`` (see ``apps/policies/enforcement.py`` +
``apps/accounts/iam_pdp_guards.py``). Remaining enforcement layers —
ReBAC sensitive-mode, richer decision logging — continue to wire in
INSIDE this module once instead of across every view that asks the
question.

Consumers must call these functions, never the underlying helpers
directly — ``scripts/scan_access_resolver_fragmentation.py`` (CI ratchet)
counts direct calls and only allows the number to go down.
"""

from __future__ import annotations

from typing import Optional


def student_data_access(user, student_id: int) -> bool:
    """May ``user`` view this student's records? (roster/360/report reads)"""
    from apps.accounts.permissions import can_view_student_data

    return can_view_student_data(user, student_id)


def student_grades_edit_access(
    user, student_id: int, subject_id: Optional[int] = None
) -> bool:
    """May ``user`` mutate this student's grades/transcript state?"""
    from apps.accounts.permissions import can_edit_student_grades

    return can_edit_student_grades(user, student_id, subject_id)


def invoice_access(user, invoice_id: int) -> bool:
    """May ``user`` view this invoice? (finance office + own-children parents)"""
    from apps.accounts.permissions import can_view_invoice

    return can_view_invoice(user, invoice_id)


def invoice_edit_access(user, invoice_id: int) -> bool:
    """May ``user`` mutate this invoice?"""
    from apps.accounts.permissions import can_edit_invoice

    return can_edit_invoice(user, invoice_id)


def module_access(user, module: str, action: str = "read") -> bool:
    """May ``user`` reach this module at all? (nav/middleware gate)"""
    from apps.accounts.permissions import can_access_module

    return can_access_module(user, module, action)


def school_permission_access(user, school, action) -> bool:
    """Membership-role gate: may ``user`` perform this SchoolAction at ``school``?"""
    from apps.schools.tenant_access import has_school_permission

    return has_school_permission(user, school, action)


def tenant_admin_access(user, school, *, codes=("settings.manage",)) -> bool:
    """May ``user`` administer this tenant? (owner / role=ADMIN / settings.manage;
    superuser bypass). The gate behind the ``tenant_admin_required`` decorator — use
    this for non-decorator (in-body / template-context) tenant-admin checks so the
    rule stays in one place."""
    from apps.accounts.decorators import user_is_tenant_admin

    return user_is_tenant_admin(user, school, codes=codes)


def permission_access(
    user,
    school,
    codes,
    *,
    allow_admin: bool = True,
    allow_roles=(),
    admin_codes=("settings.manage",),
) -> bool:
    """Additive granular-RBAC gate: may ``user`` reach a surface gated on ``codes``?

    True when ANY code is held (``has_feature_permission``, school-scoped) OR — additively —
    the caller is the tenant-admin tier (``allow_admin``) or carries an allowed role
    (``allow_roles``); superuser bypass. The resolver behind the ``require_permission``
    decorator — use this for non-decorator (in-body / template-context) granular checks so
    every surface asks the question the same way, and PDP/ReBAC/decision-logging can wire in
    here once."""
    from apps.accounts.decorators import user_has_permission

    return user_has_permission(
        user,
        school,
        codes,
        allow_admin=allow_admin,
        allow_roles=allow_roles,
        admin_codes=admin_codes,
    )


def role_access(user, role: str) -> bool:
    """Does ``user`` hold this role (hierarchy + temporary grants honoured)?"""
    from apps.accounts.permissions import has_role

    return has_role(user, role)


def any_role_access(user, roles) -> bool:
    """Does ``user`` hold ANY of these roles? (session/view contexts)"""
    from apps.accounts.permissions import has_role

    return any(has_role(user, str(r).strip().upper()) for r in roles if r)


def api_any_role_access(user, roles) -> bool:
    """DRF-safe any-role check (handles unauthenticated; role + AccessRole)."""
    from apps.accounts.permissions import api_user_has_any_role

    return api_user_has_any_role(user, roles)


__all__ = [
    "any_role_access",
    "api_any_role_access",
    "invoice_access",
    "invoice_edit_access",
    "module_access",
    "permission_access",
    "role_access",
    "school_permission_access",
    "student_data_access",
    "student_grades_edit_access",
    "tenant_admin_access",
]
