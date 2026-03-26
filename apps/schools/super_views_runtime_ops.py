"""
Runtime inspector, runtime truth hub (platform defaults read-only), and workflow simulator
(BR-12 split from super_views).
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


def super_runtime_truth_hub(request):
    """
    Read-only platform summary: RuntimeDefaults singleton + slim SiteSettings row.

    Uses ``get_platform_site_settings_record`` (platform_runtime.helpers) — same
    canonical singleton accessor as Studio rollback and backfill commands — no ad-hoc
    ORM access to the platform singleton in this view.
    """
    from apps.platform_runtime.helpers import get_platform_site_settings_record
    from apps.platform_runtime.models import RuntimeDefaults

    rt = RuntimeDefaults.get_singleton()
    payload = rt.payload if rt and isinstance(rt.payload, dict) else {}
    payload_keys = sorted(payload.keys())
    preview: list[dict[str, object]] = []
    for key in payload_keys[:48]:
        val = payload[key]
        if isinstance(val, dict):
            kind = "dict"
            extra = f"len={len(val)}"
        elif isinstance(val, list):
            kind = "list"
            extra = f"len={len(val)}"
        elif isinstance(val, bool):
            kind = "bool"
            extra = repr(val)
        elif val is None:
            kind = "null"
            extra = ""
        elif isinstance(val, (int, float)):
            kind = "number"
            extra = str(val)
        else:
            s = str(val)
            kind = "string"
            extra = s if len(s) <= 64 else s[:61] + "…"
        preview.append({"key": key, "kind": kind, "extra": extra})

    ss = get_platform_site_settings_record(create=False)
    site_settings_summary = None
    if ss is not None:
        site_settings_summary = {
            "pk": ss.pk,
            "maintenance_mode": ss.maintenance_mode,
            "updated_at": ss.updated_at,
            "has_logo": bool(getattr(ss, "logo", None)),
            "has_favicon": bool(getattr(ss, "favicon", None)),
            "theme_pack_id": getattr(ss.theme_pack, "pk", None),
            "admin_theme_pack_id": getattr(ss.admin_theme_pack, "pk", None),
        }

    return render(
        request,
        "schools/super_runtime_truth_hub.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "runtime_defaults": rt,
            "payload_key_count": len(payload_keys),
            "payload_keys_truncated": len(payload_keys) > len(preview),
            "payload_preview": preview,
            "cache_rankings_interval_minutes": getattr(
                rt, "cache_rankings_interval_minutes", None
            )
            if rt
            else None,
            "site_settings_summary": site_settings_summary,
            "decision_architecture": get_decision_architecture_for_page(
                "runtime_truth_hub"
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
