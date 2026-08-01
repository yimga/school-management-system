"""Authoritative tenant runtime-assignment readiness evidence."""

from __future__ import annotations

from typing import Any, Iterable

from django.db import DatabaseError


def _normalized_roles(roles: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(role).strip().upper() for role in roles if role))


def runtime_assignment_evidence(
    school: Any,
    *,
    user: Any = None,
    required_roles: Iterable[str] = ("ADMIN",),
) -> dict[str, Any]:
    """Return school-scoped evidence used by every setup-readiness consumer.

    Resolution follows the live runtime precedence: user preference, tenant
    layout, dashboard pack, workflow assignment, then explicit legacy fallback.
    Inactive packs/templates/assignments never count.
    """
    roles = _normalized_roles(required_roles) or ("ADMIN",)
    result: dict[str, Any] = {
        "passed": False,
        "source": "none",
        "required_roles": list(roles),
        "matched_roles": [],
        "counts": {
            "user_preferences": 0,
            "tenant_layouts": 0,
            "dashboard_packs": 0,
            "workflow_packs": 0,
            "tenant_workflows": 0,
            "legacy": 0,
        },
    }
    if school is None:
        return result

    if user is not None:
        try:
            preferences = getattr(user, "dashboard_preferences", None)
            get_pack = getattr(preferences, "get_dashboard_pack", None)
            selected_roles = [role for role in roles if callable(get_pack) and get_pack(role)]
            if selected_roles:
                result["counts"]["user_preferences"] = len(selected_roles)
                result["matched_roles"] = selected_roles
                result["source"] = "user_preference"
                result["passed"] = True
                return result
        except (AttributeError, DatabaseError, TypeError, ValueError):
            pass

    try:
        from apps.siteconfig.models_dashboard import DashboardPackAssignment, TenantLayoutAssignment

        layouts = TenantLayoutAssignment.objects.filter(
            school=school,
            role__in=roles,
            is_active=True,
            template__is_active=True,
        ).filter(
            # A layout without a pack is supported; when a pack exists it must be active.
            models.Q(template__dashboard_pack__isnull=True)
            | models.Q(template__dashboard_pack__is_active=True)
        )
        layout_roles = list(layouts.values_list("role", flat=True).distinct())
        result["counts"]["tenant_layouts"] = len(layout_roles)
        if set(roles).issubset(set(layout_roles)):
            result["matched_roles"] = layout_roles
            result["source"] = "tenant_layout"
            result["passed"] = True
            return result

        packs = DashboardPackAssignment.objects.filter(
            school=school,
            role__in=[role.lower() for role in roles] + list(roles),
            is_active=True,
            dashboard_pack__is_active=True,
        )
        pack_roles = [str(role).upper() for role in packs.values_list("role", flat=True).distinct()]
        result["counts"]["dashboard_packs"] = len(pack_roles)
        if set(roles).issubset(set(pack_roles)):
            result["matched_roles"] = pack_roles
            result["source"] = "dashboard_pack"
            result["passed"] = True
            return result
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
        pass

    try:
        from apps.siteconfig.models_workflow import TenantWorkflow, WorkflowPackAssignment

        workflow_packs = WorkflowPackAssignment.objects.filter(
            school=school, is_active=True, workflow_pack__is_active=True
        ).count()
        tenant_workflows = TenantWorkflow.objects.filter(
            school=school, is_active=True, template__is_active=True
        ).count()
        result["counts"]["workflow_packs"] = workflow_packs
        result["counts"]["tenant_workflows"] = tenant_workflows
        if workflow_packs or tenant_workflows:
            result["source"] = "workflow_assignment"
            result["passed"] = True
            return result
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
        pass

    legacy = bool(
        getattr(school, "default_dashboard_slug", None)
        or getattr(school, "default_workflow_slug", None)
    )
    result["counts"]["legacy"] = int(legacy)
    if legacy:
        result["source"] = "legacy_fallback"
        result["passed"] = True
    return result


# Imported late above models.Q would otherwise pull model modules at import time.
from django.db import models  # noqa: E402
