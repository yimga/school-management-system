"""
Help north-star executive dashboard (batch 1349) + CSV export + content gaps (1354).
"""

from __future__ import annotations

import csv
import io

from django.http import HttpResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.feedback.models import HelpContentGapTask
from apps.portal.help_content_gaps import (
    assign_content_gap,
    create_kb_draft_from_content_gap,
)
from apps.portal.help_north_star import build_north_star_bundle
from apps.schools.control_plane import require_control_plane_access
from apps.schools.operator_report_render import render_manager_report_page


def _csv_response(bundle: dict) -> HttpResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["metric", "value"])
    writer.writerow(["days", bundle.get("days", "")])
    defl = bundle.get("deflection") or {}
    for key in (
        "deflection_rate_pct",
        "suggested",
        "dismissed",
        "opened",
        "submitted",
        "total_events",
    ):
        writer.writerow([f"deflection.{key}", defl.get(key, "")])
    csat = bundle.get("csat") or {}
    for key in ("ratings_count", "thumbs_up", "thumbs_down", "avg_stars"):
        writer.writerow([f"csat.{key}", csat.get(key, "")])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="help-north-star.csv"'
    return resp


@require_http_methods(["GET", "POST"])
@require_control_plane_access
def manager_help_analytics(request):
    days = int(request.GET.get("days", "30") or 30)
    bundle = build_north_star_bundle(days=days)

    if request.GET.get("format") == "csv":
        return _csv_response(bundle)

    if request.method == "POST":
        task_id = request.POST.get("gap_id")
        action = (request.POST.get("action") or "").strip()
        row = HelpContentGapTask.objects.filter(pk=task_id).first()
        if row and action == "assign_gap":
            due_raw = (request.POST.get("due_date") or "").strip()
            due = None
            if due_raw:
                from datetime import datetime

                due = datetime.strptime(due_raw, "%Y-%m-%d").date()
            assign_content_gap(
                row,
                assignee=request.user,
                due_date=due,
                note=(request.POST.get("note") or "").strip(),
            )
        elif row and action == "draft_gap_kb":
            try:
                create_kb_draft_from_content_gap(row, author=request.user)
            except ValueError:
                pass
        elif row and action == "done_gap":
            row.status = HelpContentGapTask.Status.DONE
            row.save(update_fields=["status", "updated_at"])
        return HttpResponse(status=302, headers={"Location": request.path})

    gaps = list(
        HelpContentGapTask.objects.filter(
            status__in=[
                HelpContentGapTask.Status.OPEN,
                HelpContentGapTask.Status.ASSIGNED,
                HelpContentGapTask.Status.DRAFTED,
            ]
        ).select_related("assigned_to", "kb_draft_article")[:50]
    )

    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_help_analytics_body.html",
        context={
            "north_star": bundle,
            "content_gaps": gaps,
            "help_center_url": reverse("manager_help_center"),
            "ai_review_url": reverse("manager_ai_review_queue"),
            "locale_families_url": reverse("manager_kb_locale_families"),
            "days": days,
        },
        page_title=str(_("Help analytics")),
        page_archetype="operational-workbench",
    )
