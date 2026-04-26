# -*- coding: utf-8 -*-
"""
Read-only academic year setup evidence (per-tenant AcademicYear rows). No rollover or CRUD here.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.accounts.decorators import permission_required

logger = logging.getLogger(__name__)


@login_required
@permission_required("settings.manage", raise_exception=True)
def academic_years_setup_evidence(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    rows: list = []
    year_total = 0
    year_active = 0
    year_locked = 0
    if school is not None:
        try:
            from apps.academics.models import AcademicYear

            base = AcademicYear.objects.filter(school_id=school.id)
            year_total = base.count()
            year_active = base.filter(is_active=True).count()
            year_locked = base.filter(is_locked=True).count()
            rows = list(
                base.order_by("-start_date", "name", "id")[:150]
            )
        except Exception as ex:  # noqa: BLE001
            logger.debug("academic_years_setup_evidence: %s", ex)
    # Academics are registered on tenant admin only; ROOT_URLCONF hosts platform admin.
    try:
        admin_changelist = reverse(
            "admin:academics_academicyear_changelist",
            urlconf="config.tenant_urls",
        )
    except NoReverseMatch:
        admin_changelist = ""
    try:
        sched_hub = reverse("siteconfig:scheduled_reports_delivery_hub")
    except NoReverseMatch:
        sched_hub = ""
    try:
        departments_url = reverse("siteconfig:departments_setup_evidence")
    except NoReverseMatch:
        departments_url = ""
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
    return render(
        request,
        "siteconfig/academic_years_setup_evidence.html",
        {
            "school": school,
            "rows": rows,
            "admin_academic_year_changelist_url": admin_changelist,
            "scheduled_reports_hub_url": sched_hub,
            "departments_setup_evidence_url": departments_url,
            "term_publish_status_evidence_url": term_publish_evidence_url,
            "tenant_report_schedules_evidence_url": tenant_report_schedules_evidence_url,
            "year_total": year_total,
            "year_active": year_active,
            "year_locked": year_locked,
        },
    )
