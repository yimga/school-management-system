# -*- coding: utf-8 -*-
"""1072: Read-only report output history evidence from real ReportCard rows."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_stem,
)
from django.utils.translation import gettext as _

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

    report_q.count()
    report_q.exclude(pdf_file="").count()
    report_ids = report_q.values_list("pk", flat=True)
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    ReportDocumentHash.objects.filter(report_card_id__in=report_ids).count()
    ReportCardAudit.objects.filter(report_card_id__in=report_ids).count()
    list(report_q.order_by("-generated_at")[:100])

    if getattr(request.user, "is_superuser", False):
        _safe_reverse(
            "admin:reports_reportcard_changelist"
        )

    return render_siteconfig_stem(
        request,
        "report_output_history_evidence",
        None,
        cp_title=_("Report output history"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Report output history"), active=True),
        ),
    )
