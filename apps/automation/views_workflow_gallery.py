"""Read-only workflow template gallery (staff)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.automation.workflow_template_gallery import (
    GALLERY_TEMPLATE_DRY_RUN_TRIGGER,
    WORKFLOW_TEMPLATE_GALLERY,
)


def _staff_required(user):
    return getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)


@login_required
@user_passes_test(_staff_required)
def workflow_template_gallery(request):
    school = getattr(request, "school", None)
    items = []
    for row in WORKFLOW_TEMPLATE_GALLERY:
        r = dict(row)
        sim = r.get("simulate_url_name")
        des = r.get("designer_url_name")
        hint = r.get("gallery_hint") or ""
        try:
            r["simulate_url"] = reverse(sim) if sim else ""
        except NoReverseMatch:
            r["simulate_url"] = ""
        tid = r.get("id") or ""
        try:
            r["dry_run_url"] = (
                reverse(
                    "automation:workflow_template_dry_run",
                    kwargs={"template_id": tid},
                )
                if tid
                else ""
            )
        except NoReverseMatch:
            r["dry_run_url"] = ""
        r["designer_url"] = ""
        if school:
            try:
                base = reverse(des) if des else ""
                r["designer_url"] = (
                    f"{base}?gallery_hint={hint}" if base and hint else base
                )
            except NoReverseMatch:
                r["designer_url"] = ""
        items.append(r)
    return render(
        request,
        "automation/workflow_template_gallery.html",
        {
            "templates": items,
            "page_title": "Workflow template gallery",
        },
    )


@login_required
@user_passes_test(_staff_required)
def workflow_template_dry_run(request, template_id: str):
    """One-click dry-run: simulate published workflow for trigger, else synthetic sample JSON."""
    from apps.automation.visual_executor import simulate_workflow
    from apps.automation.workflow_graph_models import Workflow
    from apps.automation.workflow_trigger_catalog import sample_payload_for_trigger

    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": "no_school_context"}, status=400)
    trigger = GALLERY_TEMPLATE_DRY_RUN_TRIGGER.get(template_id)
    if not trigger:
        return JsonResponse({"ok": False, "error": "unknown_template"}, status=404)
    sid = str(school.pk)
    payload = sample_payload_for_trigger(sid, trigger)
    wf = (
        Workflow.objects.filter(
            school=school,
            trigger_event=trigger,
            status=Workflow.Status.PUBLISHED,
            is_active=True,
        )
        .order_by("-updated_at")
        .first()
    )
    if wf:
        result = simulate_workflow(wf.pk, payload, user=request.user)
        return JsonResponse(
            {
                "ok": True,
                "mode": "published_workflow",
                "workflow_id": wf.pk,
                "trigger_key": trigger,
                "result": result,
            }
        )
    return JsonResponse(
        {
            "ok": True,
            "mode": "synthetic_dry_run",
            "trigger_key": trigger,
            "sample_payload": payload,
            "note": (
                "No published workflow for this trigger on this tenant — "
                "synthetic sample only."
            ),
        }
    )
