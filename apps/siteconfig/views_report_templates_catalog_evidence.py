# -*- coding: utf-8 -*-
"""
Read-only catalog of ReportTemplate rows (1072) — same family filter as report download.
No export on this view; use download_report or management flows for files.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.accounts.decorators import permission_required
from apps.siteconfig.models import ReportTemplate
from apps.siteconfig.models_tooling import REPORT_EXPORT_HANDLERS
from apps.siteconfig.tenant_config import get_report_template_family_for_school


@login_required
@permission_required("settings.manage", raise_exception=True)
def report_templates_catalog_evidence(
    request: HttpRequest,
) -> HttpResponse:
    school = getattr(request, "school", None)
    report_template_family = ""
    qs = ReportTemplate.objects.filter(is_active=True)
    if school is not None:
        report_template_family = (
            get_report_template_family_for_school(school) or ""
        ).strip()
        if report_template_family:
            qs = qs.filter(
                Q(template_family="") | Q(template_family=report_template_family)
            )
    template_rows: list[dict] = []
    for t in qs.order_by("name")[:200]:
        has_handler = t.slug in REPORT_EXPORT_HANDLERS
        template_rows.append(
            {
                "template": t,
                "has_export_handler": has_handler,
            }
        )
    template_with_handler = sum(1 for r in template_rows if r["has_export_handler"])

    admin_reporttemplate_changelist_url = None
    u = request.user
    if getattr(u, "is_authenticated", False) and getattr(u, "is_superuser", False):
        try:
            admin_reporttemplate_changelist_url = reverse(
                "admin:siteconfig_reporttemplate_changelist"
            )
        except NoReverseMatch:
            pass

    scheduled_reports_hub_url = None
    try:
        scheduled_reports_hub_url = reverse("siteconfig:scheduled_reports_delivery_hub")
    except NoReverseMatch:
        pass
    tenant_report_schedules_evidence_url = None
    try:
        tenant_report_schedules_evidence_url = reverse(
            "siteconfig:tenant_report_schedules_evidence"
        )
    except NoReverseMatch:
        pass
    try:
        term_publish_status_evidence_url = reverse(
            "siteconfig:term_publish_status_evidence"
        )
    except NoReverseMatch:
        term_publish_status_evidence_url = None

    return render(
        request,
        "siteconfig/report_templates_catalog_evidence.html",
        {
            "school": school,
            "template_rows": template_rows,
            "template_total": len(template_rows),
            "template_with_handler": template_with_handler,
            "report_template_family": report_template_family,
            "admin_reporttemplate_changelist_url": admin_reporttemplate_changelist_url,
            "scheduled_reports_hub_url": scheduled_reports_hub_url,
            "tenant_report_schedules_evidence_url": tenant_report_schedules_evidence_url,
            "term_publish_status_evidence_url": term_publish_status_evidence_url,
        },
    )
