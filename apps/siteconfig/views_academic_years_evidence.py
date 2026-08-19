# -*- coding: utf-8 -*-
"""
Academic year lifecycle control + setup evidence (Configuration Engine lane).

Read table plus Soft Close / activate / soft-reopen actions for settings.manage.
Hard-close unlock remains Django admin break-glass (batch 1800).
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_stem,
)

logger = logging.getLogger(__name__)


def _lifecycle_redirect() -> HttpResponseRedirect:
    return HttpResponseRedirect(reverse("siteconfig:academic_years_setup_evidence"))


@login_required
@permission_required("settings.manage", raise_exception=True)
@require_http_methods(["GET", "POST"])
def academic_years_setup_evidence(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)

    if request.method == "POST" and school is not None:
        action = (request.POST.get("lifecycle_action") or "").strip()
        year_id = (request.POST.get("year_id") or "").strip()
        reason = (request.POST.get("reason") or "").strip()
        try:
            from apps.academics.models import AcademicYear
            from apps.academics.year_close import (
                activate_academic_year,
                reopen_soft_closed_year,
                soft_close_academic_year,
            )

            year = AcademicYear.objects.filter(school=school, pk=year_id).first()
            if year is None:
                messages.error(request, _("Academic year not found for this school."))
            elif action == "activate":
                activate_academic_year(school, year, actor=request.user)
                messages.success(
                    request,
                    _("Set %(name)s as the active (default) year.")
                    % {"name": year.name},
                )
            elif action == "soft_close":
                soft_close_academic_year(
                    school,
                    year,
                    actor=request.user,
                    reason=reason or "lifecycle control soft close",
                )
                messages.success(
                    request,
                    _("Soft-closed %(name)s — teachers cannot enter grades.")
                    % {"name": year.name},
                )
            elif action == "soft_reopen":
                reopen_soft_closed_year(
                    school,
                    year,
                    actor=request.user,
                    reason=reason or "lifecycle control soft reopen",
                )
                messages.success(
                    request,
                    _("Reopened soft-close on %(name)s.") % {"name": year.name},
                )
            else:
                messages.error(request, _("Unknown lifecycle action."))
        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as ex:  # noqa: BLE001
            logger.exception("academic_years lifecycle action failed: %s", ex)
            messages.error(request, _("Could not apply lifecycle action."))
        return _lifecycle_redirect()

    ctx: dict = {"school": school, "lifecycle_control": True}
    if school is not None:
        try:
            from apps.academics.models import AcademicYear

            base = AcademicYear.objects.filter(school_id=school.id)
            ctx["year_total"] = base.count()
            ctx["year_active"] = base.filter(is_active=True).count()
            ctx["year_soft_closed"] = base.filter(
                is_soft_closed=True, is_locked=False
            ).count()
            ctx["year_locked"] = base.filter(is_locked=True).count()
            ctx["rows"] = list(base.order_by("-start_date", "name", "id")[:150])
        except Exception as ex:  # noqa: BLE001
            logger.debug("academic_years_setup_evidence: %s", ex)
    try:
        ctx["admin_academic_year_changelist_url"] = reverse(
            "admin:academics_academicyear_changelist",
            urlconf="config.tenant_urls",
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
        ctx["departments_setup_evidence_url"] = reverse(
            "siteconfig:departments_setup_evidence"
        )
    except NoReverseMatch:
        pass
    try:
        ctx["term_publish_status_evidence_url"] = reverse(
            "siteconfig:term_publish_status_evidence"
        )
    except NoReverseMatch:
        pass
    try:
        ctx["tenant_report_schedules_evidence_url"] = reverse(
            "siteconfig:tenant_report_schedules_evidence"
        )
    except NoReverseMatch:
        pass
    try:
        ctx["rollover_url"] = reverse("accounts:rollover_year")
    except NoReverseMatch:
        pass
    return render_siteconfig_stem(
        request,
        "academic_years_setup_evidence",
        ctx,
        cp_title=_("Academic years lifecycle"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Academic years lifecycle"), active=True),
        ),
    )
