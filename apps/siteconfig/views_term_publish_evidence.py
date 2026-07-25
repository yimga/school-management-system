# -*- coding: utf-8 -*-
"""
Read-only term publish / report-card publish status (TermPublishStatus). No publish actions here.
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
def term_publish_status_evidence(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    ctx: dict = {"school": school}
    if school is not None:
        try:
            from apps.reports.models import TermPublishStatus

            base = TermPublishStatus.objects.filter(
                academic_year__school_id=school.id
            )
            ctx["tps_total"] = base.count()
            ctx["tps_published"] = base.filter(is_published=True).count()
            ctx["rows"] = list(
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
        ctx["admin_termpublish_changelist_url"] = reverse(
            "admin:reports_termpublishstatus_changelist"
        )
    except NoReverseMatch:
        pass
    try:
        ctx["scheduled_reports_hub_url"] = reverse(
            "siteconfig:scheduled_reports_delivery_hub"
        )
    except NoReverseMatch:
        pass
    try:
        ctx["academic_years_setup_evidence_url"] = reverse(
            "siteconfig:academic_years_setup_evidence"
        )
    except NoReverseMatch:
        pass
    try:
        ctx["tenant_report_schedules_evidence_url"] = reverse(
            "siteconfig:tenant_report_schedules_evidence"
        )
    except NoReverseMatch:
        pass
    return render_siteconfig_stem(
        request,
        "term_publish_status_evidence",
        ctx,
        cp_title=_("Term publish status"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Term publish status"), active=True),
        ),
    )
