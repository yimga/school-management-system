# -*- coding: utf-8 -*-
"""
Read-only catalog of ReportTemplate rows (1072) — same family filter as report download.
No export on this view; use download_report or management flows for files.
"""

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
    sum(1 for r in template_rows if r["has_export_handler"])

    u = request.user
    if getattr(u, "is_authenticated", False) and getattr(u, "is_superuser", False):
        try:
            reverse(
                "admin:siteconfig_reporttemplate_changelist"
            )
        except NoReverseMatch:
            pass

    try:
        reverse("siteconfig:scheduled_reports_delivery_hub")
    except NoReverseMatch:
        pass
    try:
        reverse(
            "siteconfig:tenant_report_schedules_evidence"
        )
    except NoReverseMatch:
        pass
    try:
        reverse(
            "siteconfig:term_publish_status_evidence"
        )
    except NoReverseMatch:
        pass
    try:
        reverse("siteconfig:compliance_exports")
    except NoReverseMatch:
        pass

    return render_siteconfig_stem(
        request,
        "report_templates_catalog_evidence",
        None,
        cp_title=_("Report templates catalog"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Report templates catalog"), active=True),
        ),
    )
