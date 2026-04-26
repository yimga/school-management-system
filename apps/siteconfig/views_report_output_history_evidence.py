# -*- coding: utf-8 -*-
"""1072: Read-only report output history evidence from real ReportCard rows."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.accounts.decorators import permission_required
from apps.reports.models import ReportCard, ReportCardAudit, ReportDocumentHash


def _safe_reverse(name: str) -> str | None:
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


@login_required
@permission_required("settings.manage", raise_exception=True)
def report_output_history_evidence(request: HttpRequest) -> HttpResponse:
    """Evidence-only view of generated report-card output rows and hash coverage."""
    school = getattr(request, "school", None)
    report_q = ReportCard.objects.none()
    if school is not None:
        report_q = (
            ReportCard.objects.filter(Q(school=school) | Q(student__school=school))
            .select_related("student", "academic_year", "term")
            .distinct()
        )

    report_total = report_q.count()
    pdf_total = report_q.exclude(pdf_file="").count()
    report_ids = report_q.values_list("pk", flat=True)
    hash_total = ReportDocumentHash.objects.filter(report_card_id__in=report_ids).count()
    audit_total = ReportCardAudit.objects.filter(report_card_id__in=report_ids).count()
    recent_reports = list(report_q.order_by("-generated_at")[:100])

    admin_reportcard_changelist_url = None
    if getattr(request.user, "is_superuser", False):
        admin_reportcard_changelist_url = _safe_reverse(
            "admin:reports_reportcard_changelist"
        )

    return render(
        request,
        "siteconfig/report_output_history_evidence.html",
        {
            "school": school,
            "recent_reports": recent_reports,
            "report_total": report_total,
            "pdf_total": pdf_total,
            "hash_total": hash_total,
            "audit_total": audit_total,
            "scheduled_reports_hub_url": _safe_reverse(
                "siteconfig:scheduled_reports_delivery_hub"
            ),
            "tenant_report_schedules_evidence_url": _safe_reverse(
                "siteconfig:tenant_report_schedules_evidence"
            ),
            "report_templates_catalog_url": _safe_reverse(
                "siteconfig:report_templates_catalog_evidence"
            ),
            "term_publish_status_evidence_url": _safe_reverse(
                "siteconfig:term_publish_status_evidence"
            ),
            "admin_reportcard_changelist_url": admin_reportcard_changelist_url,
        },
    )
