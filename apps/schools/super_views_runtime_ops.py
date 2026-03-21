"""
Runtime inspector and workflow simulator (BR-12 split from super_views).
"""

from __future__ import annotations

from django.shortcuts import render
from django.urls import reverse

from .decision_architecture import get_decision_architecture_for_page
from .models import School


def super_runtime_inspector(request):
    """Control plane: inspect tenant_runtime for a selected school (effective blueprint, packs, overrides)."""
    from apps.platform_runtime.runtime_inspector import (
        get_runtime_inspection_for_school,
    )

    school_id = (request.GET.get("school_id") or "").strip()
    school = None
    inspection = None
    schools_sample = list(
        School.objects.filter(is_active=True)
        .order_by("-last_activity", "-created_at")[:20]
        .values("id", "name", "slug")
    )
    if school_id:
        try:
            school = School.objects.get(id=school_id)
            inspection = get_runtime_inspection_for_school(school)
        except (School.DoesNotExist, ValueError):
            pass
    return render(
        request,
        "schools/super_runtime_inspector.html",
        {
            "school": school,
            "inspection": inspection,
            "schools_sample": schools_sample,
            "dashboard_url": reverse("super:dashboard"),
            "decision_architecture": get_decision_architecture_for_page(
                "runtime_inspector"
            ),
        },
    )


def super_workflow_simulator(request):
    """Control plane: simulate workflow/pack resolution for a selected school and role."""
    school_id = (request.GET.get("school_id") or "").strip()
    role = (request.GET.get("role") or "ADMIN").strip().upper()
    school = None
    workflow_summary = None
    if school_id:
        try:
            school = School.objects.get(id=school_id)
            from apps.platform_runtime.runtime_resolver import (
                build_tenant_runtime_for_tenant,
            )

            rt = build_tenant_runtime_for_tenant(
                school, user=getattr(request, "user", None)
            )
            if rt and hasattr(rt, "workflow_for"):
                wf = rt.workflow_for(role)
                workflow_summary = {
                    "role": role,
                    "workflow_id": getattr(wf, "id", None),
                    "workflow_slug": getattr(wf, "slug", None),
                }
            elif rt and hasattr(rt, "policy"):
                workflow_summary = {
                    "role": role,
                    "workflow_id": None,
                    "workflow_slug": None,
                    "note": "workflow_for not available",
                }
        except (School.DoesNotExist, ValueError):
            pass
    return render(
        request,
        "schools/super_workflow_simulator.html",
        {
            "school": school,
            "workflow_summary": workflow_summary,
            "dashboard_url": reverse("super:dashboard"),
        },
    )
