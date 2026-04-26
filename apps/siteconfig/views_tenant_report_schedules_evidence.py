# -*- coding: utf-8 -*-
"""1099: Read-only TenantReportSchedule evidence (operator) — real schedule rows only."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.accounts.decorators import permission_required
from apps.reports.models import TenantReportSchedule


def _safe_reverse(name: str) -> str | None:
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


@login_required
@permission_required("settings.manage", raise_exception=True)
def tenant_report_schedules_evidence(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    schedules: list[TenantReportSchedule] = []
    schedule_total = 0
    schedule_active = 0
    schedule_due = 0
    schedule_missing_recipients = 0
    schedule_last_run_total = 0
    now = timezone.now()
    if school is not None:
        qs = TenantReportSchedule.objects.filter(school=school)
        schedule_total = qs.count()
        act = qs.filter(is_active=True)
        schedule_active = act.count()
        schedule_due = act.filter(next_run__lte=now).count()
        schedule_last_run_total = qs.exclude(last_run__isnull=True).count()
        missing = 0
        for row in act.only("id", "recipients"):
            r = row.recipients
            if not isinstance(r, list) or len(r) == 0:
                missing += 1
        schedule_missing_recipients = missing
        schedules = list(qs.order_by("next_run")[:200])

    tenant_report_schedule_admin_url = None
    u = request.user
    if (
        u is not None
        and getattr(u, "is_authenticated", False)
        and getattr(u, "is_staff", False)
    ):
        tenant_report_schedule_admin_url = _safe_reverse(
            "admin:reports_tenantreportschedule_changelist"
        )
    reports_scheduled_api_list_url = _safe_reverse("api_v1:reports-scheduled-list")

    ctx: dict = {
        "school": school,
        "schedules": schedules,
        "schedule_total": schedule_total,
        "schedule_active": schedule_active,
        "schedule_due": schedule_due,
        "schedule_missing_recipients": schedule_missing_recipients,
        "schedule_last_run_total": schedule_last_run_total,
        "tenant_report_schedule_admin_url": tenant_report_schedule_admin_url,
        "reports_scheduled_api_list_url": reports_scheduled_api_list_url,
        "operator_bulk_letters_url": _safe_reverse("siteconfig:bulk_letters"),
        "operator_term_publish_evidence_url": _safe_reverse(
            "siteconfig:term_publish_status_evidence"
        ),
        "operator_academic_years_evidence_url": _safe_reverse(
            "siteconfig:academic_years_setup_evidence"
        ),
        "operator_departments_setup_evidence_url": _safe_reverse(
            "siteconfig:departments_setup_evidence"
        ),
        "operator_report_templates_catalog_url": _safe_reverse(
            "siteconfig:report_templates_catalog_evidence"
        ),
        "operator_report_output_history_evidence_url": _safe_reverse(
            "siteconfig:report_output_history_evidence"
        ),
    }
    return render(
        request,
        "siteconfig/tenant_report_schedules_evidence.html",
        ctx,
    )
