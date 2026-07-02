"""Canonical effective-access facade (sovereign consolidation, 2026-07-02).

THE single consumer entry point for object/module access decisions. The
platform's authorization intent converges here: today each function
delegates verbatim to the battle-tested helper that owns the rule (so
behavior is bit-identical to the pre-facade call-sites), and future
enforcement layers — PDP ``decide()`` promotion past advisory, ReBAC
sensitive-mode, decision logging — get wired INSIDE this module once
instead of across every view that asks the question.

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
    "role_access",
    "school_permission_access",
    "student_data_access",
    "student_grades_edit_access",
]
