# -*- coding: utf-8 -*-
"""
Read-only term publish / report-card publish status (TermPublishStatus). No publish actions here.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_stem,
)
from django.utils.translation import gettext as _

from django.urls import NoReverseMatch, reverse

from apps.accounts.decorators import permission_required

logger = logging.getLogger(__name__)


@login_required
@permission_required("settings.manage", raise_exception=True)
def term_publish_status_evidence(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    rows: list = []
    tps_total = 0
    tps_published = 0
    if school is not None:
        try:
            from apps.reports.models import TermPublishStatus

            base = TermPublishStatus.objects.filter(
                academic_year__school_id=school.id
            )
            tps_total = base.count()
            tps_published = base.filter(is_published=True).count()
            rows = list(
                base.select_related(
                    "academic_year", "term", "classroom", "published_by"
                )
                .order_by(
                    "-published_at",
                    "academic_year__name",
                    "term__position",
                    "term__name",
                    "id",
                )[:200]
            )
        except Exception as ex:  # noqa: BLE001 — read-only; surface empty on DB edge
            logger.debug("term_publish_status_evidence: %s", ex)
    try:
        admin_list = reverse("admin:reports_termpublishstatus_changelist")
    except NoReverseMatch:
        admin_list = ""
    try:
        sched_hub = reverse("siteconfig:scheduled_reports_delivery_hub")
    except NoReverseMatch:
        sched_hub = ""
    try:
        academic_years_evidence = reverse("siteconfig:academic_years_setup_evidence")
    except NoReverseMatch:
        academic_years_evidence = ""
    try:
        tenant_sched_evidence = reverse("siteconfig:tenant_report_schedules_evidence")
    except NoReverseMatch:
        tenant_sched_evidence = ""
    return render_siteconfig_stem(
        request,
        "term_publish_status_evidence",
        None,
        cp_title=_("Term publish status"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Term publish status"), active=True),
        ),
    )
