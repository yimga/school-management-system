"""
Setup Studio tenant boundary helpers — onboarding config must not cross tenants.
"""

from __future__ import annotations

from typing import Any


class SetupStudioTenantScopeError(PermissionError):
    """Setup mutations attempted across tenant boundaries."""

    pass


def assert_same_school(request_school, target_school, *, field: str = "school") -> None:
    """Raise when operator/session school does not match the mutation target."""
    req_id = getattr(request_school, "pk", None)
    tgt_id = getattr(target_school, "pk", None)
    if req_id is None or tgt_id is None or req_id != tgt_id:
        raise SetupStudioTenantScopeError(
            f"Cross-tenant setup mutation blocked for {field} "
            f"(request={req_id}, target={tgt_id})."
        )


def scoped_setup_progress_queryset(school):
    """Return SetupProgress rows for exactly one school."""
    from apps.setup_studio.models import SetupProgress

    school_id = getattr(school, "pk", None)
    if school_id is None:
        return SetupProgress.objects.none()
    return SetupProgress.objects.filter(school_id=school_id)


def compile_setup_for_school(request_school, target_school) -> dict[str, Any]:
    """Compile setup payload only when tenant scope matches."""
    assert_same_school(request_school, target_school)
    from apps.setup_studio.services import get_setup_studio_payload

    return get_setup_studio_payload(target_school)


__all__ = [
    "SetupStudioTenantScopeError",
    "assert_same_school",
    "compile_setup_for_school",
    "scoped_setup_progress_queryset",
]
