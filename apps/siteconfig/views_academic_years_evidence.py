# -*- coding: utf-8 -*-
"""
Read-only academic year setup evidence (per-tenant AcademicYear rows). No rollover or CRUD here.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
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
def academic_years_setup_evidence(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    if school is not None:
        try:
            from apps.academics.models import AcademicYear

            base = AcademicYear.objects.filter(school_id=school.id)
            base.count()
            base.filter(is_active=True).count()
            base.filter(is_locked=True).count()
            list(
                base.order_by("-start_date", "name", "id")[:150]
            )
        except Exception as ex:  # noqa: BLE001
            logger.debug("academic_years_setup_evidence: %s", ex)
    # Academics are registered on tenant admin only; ROOT_URLCONF hosts platform admin.
    try:
        reverse(
            "admin:academics_academicyear_changelist",
            urlconf="config.tenant_urls",
        )
    except NoReverseMatch:
        pass
    try:
        reverse("siteconfig:scheduled_reports_delivery_hub")
    except NoReverseMatch:
        pass
    try:
        reverse("siteconfig:departments_setup_evidence")
    except NoReverseMatch:
        pass
    try:
        reverse("siteconfig:term_publish_status_evidence")
    except NoReverseMatch:
        pass
    try:
        reverse(
            "siteconfig:tenant_report_schedules_evidence"
        )
    except NoReverseMatch:
        pass
    return render_siteconfig_stem(
        request,
        "academic_years_setup_evidence",
        None,
        cp_title=_("Academic years setup"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Academic years setup"), active=True),
        ),
    )
