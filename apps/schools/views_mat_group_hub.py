"""Wave P-A (v3.95.1 — 2026-05-26) — MAT Group Hub operator dashboard view.

Renders the cross-tenant rollup. Operator-only (staff_member_required).

Tenant isolation: the per-member metric runner is a closure over Django ORM
queries that EACH explicitly scope to the member tenant. No cross-tenant
queryset.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from .forms_mat_group_hub import (
    MATGroupEditorForm,
    apply_form_to_payload,
    load_form_initial_from_payload,
)
from .mat_group_hub import (
    MATMember,
    aggregate_group_kpis,
    find_group_by_id,
    load_registry_from_operator_settings,
)


logger = logging.getLogger(__name__)


def _default_member_metric_runner(tenant_slug: str, member: MATMember) -> dict:
    """Stub runner — returns zeros. Real deployments inject a runner that
    queries each member's School-scoped models.

    This stub keeps the dashboard renderable in dev / before per-tenant
    plumbing exists.
    """
    return {
        "students": 0,
        "staff": 0,
        "admissions_pipeline": 0,
        "fees_collected_minor": 0,
        "fees_outstanding_minor": 0,
        "attendance_rate_pct": 0.0,
        "pass_rate_pct": 0.0,
    }


def _runner_from_real_models() -> callable:
    """Build a runner that hits real models. Failures fall back to zeros so
    one bad tenant doesn't abort the rollup."""
    def runner(tenant_slug: str, member: MATMember) -> dict:
        out = _default_member_metric_runner(tenant_slug, member)
        try:
            from apps.schools.models import School  # type: ignore
            school = School.objects.filter(slug=tenant_slug).first()
            if school is None:
                return out
            # Students count
            try:
                from apps.people.models import Student  # type: ignore
                out["students"] = Student.objects.filter(school=school).count()
            except Exception:  # noqa: BLE001
                pass
            # Staff count
            try:
                from apps.people.models import Staff  # type: ignore
                out["staff"] = Staff.objects.filter(school=school).count()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mat_group_hub real-models runner failed tenant=%s err=%s",
                tenant_slug, exc,
            )
        return out
    return runner


@staff_member_required
@require_GET
def mat_group_hub_dashboard(request: HttpRequest) -> HttpResponse:
    """Operator landing page — lists every MAT group + rollup summary."""
    groups = load_registry_from_operator_settings()
    snapshots = []
    runner = _runner_from_real_models()
    for g in groups:
        snap = aggregate_group_kpis(g, tenant_scope_runner=runner)
        snapshots.append({
            "group": g,
            "snapshot": snap,
        })
    ctx = {
        "page_title": "MAT Group Hub",
        "groups_count": len(groups),
        "snapshots": snapshots,
    }
    return render(request, "schools/mat_group_hub/dashboard.html", ctx)


@staff_member_required
@require_GET
def mat_group_hub_detail(request: HttpRequest, group_id: str) -> HttpResponse:
    """One MAT group's detail view."""
    groups = load_registry_from_operator_settings()
    group = find_group_by_id(groups, group_id)
    if group is None:
        return HttpResponse("MAT group not found", status=404)
    runner = _runner_from_real_models()
    snapshot = aggregate_group_kpis(group, tenant_scope_runner=runner)
    return render(request, "schools/mat_group_hub/detail.html", {
        "page_title": f"MAT — {group.display_name}",
        "group": group,
        "snapshot": snapshot,
    })


def _get_operator_site_settings():
    """Pull the operator-side SiteSettings singleton (school=None)."""
    try:
        from apps.platform_runtime.helpers import get_platform_site_settings_record
    except Exception:  # noqa: BLE001
        return None
    return get_platform_site_settings_record(create=False)


@staff_member_required
@require_http_methods(["GET", "POST"])
def mat_group_hub_edit(request: HttpRequest, group_id: str = "") -> HttpResponse:
    """Operator UI to add / edit / delete a MAT group entry.

    URL: /super/mat-hub/edit/         → create new group
    URL: /super/mat-hub/edit/<id>/    → edit existing group
    """
    settings_row = _get_operator_site_settings()
    if settings_row is None:
        return HttpResponse(
            "Operator SiteSettings singleton not configured.",
            status=500,
        )
    payload = settings_row.cockpit_payload if isinstance(
        settings_row.cockpit_payload, dict,
    ) else {}

    if request.method == "POST":
        form = MATGroupEditorForm(request.POST)
        if form.is_valid():
            new_payload = apply_form_to_payload(payload, form)
            settings_row.cockpit_payload = new_payload
            settings_row.save(update_fields=["cockpit_payload"])
            verb = "deleted" if form.cleaned_data.get("delete") else "saved"
            messages.success(
                request,
                f"MAT group {form.cleaned_data['group_id']!r} {verb}.",
            )
            return redirect(reverse("super:mat_group_hub_dashboard"))
    else:
        initial = (
            load_form_initial_from_payload(payload, group_id)
            if group_id else {}
        )
        form = MATGroupEditorForm(initial=initial)

    return render(request, "schools/mat_group_hub/edit.html", {
        "page_title": ("Edit MAT group" if group_id else "Add MAT group"),
        "form": form,
        "group_id": group_id,
        "is_new": not group_id,
    })


@staff_member_required
@require_GET
def mat_group_hub_api(request: HttpRequest, group_id: str) -> JsonResponse:
    """JSON endpoint for the rollup — used by JS widgets + external tools."""
    groups = load_registry_from_operator_settings()
    group = find_group_by_id(groups, group_id)
    if group is None:
        return JsonResponse({"error": "group_not_found"}, status=404)
    snapshot = aggregate_group_kpis(group, tenant_scope_runner=_runner_from_real_models())
    return JsonResponse({
        "group_id": group.group_id,
        "display_name": group.display_name,
        "member_count": snapshot.member_count,
        "totals": {
            "students": snapshot.total_students,
            "staff": snapshot.total_staff,
            "admissions_pipeline": snapshot.admissions_pipeline_count,
            "fees_collected_minor": snapshot.fees_collected_minor,
            "fees_outstanding_minor": snapshot.fees_outstanding_minor,
            "attendance_rate_pct": snapshot.attendance_rate_pct,
            "pass_rate_pct": snapshot.pass_rate_pct,
        },
        "per_member": snapshot.per_member,
        "failed_members": snapshot.failed_members,
    })
