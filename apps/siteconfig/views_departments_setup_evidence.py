# -*- coding: utf-8 -*-
"""
Read-only department setup evidence (per-tenant Department rows). No CRUD here.
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
def departments_setup_evidence(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    rows: list = []
    department_total = 0
    if school is not None:
        try:
            from apps.academics.models import Department

            base = Department.objects.filter(school_id=school.id)
            department_total = base.count()
            rows = list(base.order_by("name", "id")[:200])
        except Exception as ex:  # noqa: BLE001
            logger.debug("departments_setup_evidence: %s", ex)
    # Academics are registered on tenant admin only; ROOT_URLCONF hosts platform admin.
    try:
        admin_changelist = reverse(
            "admin:academics_department_changelist",
            urlconf="config.tenant_urls",
        )
    except NoReverseMatch:
        admin_changelist = ""
    try:
        sched_hub = reverse("siteconfig:scheduled_reports_delivery_hub")
    except NoReverseMatch:
        sched_hub = ""
    try:
        academic_years_url = reverse("siteconfig:academic_years_setup_evidence")
    except NoReverseMatch:
        academic_years_url = ""
    try:
        term_publish_evidence_url = reverse("siteconfig:term_publish_status_evidence")
    except NoReverseMatch:
        term_publish_evidence_url = ""
    try:
        tenant_report_schedules_evidence_url = reverse(
            "siteconfig:tenant_report_schedules_evidence"
        )
    except NoReverseMatch:
        tenant_report_schedules_evidence_url = ""
    return render_siteconfig_stem(
        request,
        "departments_setup_evidence",
        None,
        cp_title=_("Departments setup"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Departments setup"), active=True),
        ),
    )
