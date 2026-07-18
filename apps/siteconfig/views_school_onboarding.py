# -*- coding: utf-8 -*-
"""School activation checklist (data-driven + optional operator mark-complete)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_stem,
)
from django.views.decorators.http import require_POST

from apps.lifecycle.tenant_school_resolve import require_tenant_lifecycle_school
from apps.platform_runtime.customer_health import (
    calculate_school_health,
    get_school_health_recommendations,
)
from apps.platform_runtime.onboarding import (
    get_onboarding_steps,
    get_school_onboarding_progress,
    mark_school_onboarding_step_complete,
)
from apps.platform_runtime.operational_center_nav import onboarding_activation_frame_context


def _reverse_tenant_onboarding() -> str:
    try:
        return reverse("siteconfig:onboarding", urlconf="config.tenant_urls")
    except NoReverseMatch:
        return "/siteconfig/onboarding/"


@login_required
def school_activation_onboarding(request: HttpRequest) -> HttpResponse:
    school, denied = require_tenant_lifecycle_school(request)
    if denied is not None:
        return denied
    progress: dict = {}
    health: dict = {}
    recommendations: list = []
    misconfiguration_flags: list[str] = []
    if school is not None:
        progress = get_school_onboarding_progress(school, user=request.user)
        health = calculate_school_health(school)
        recommendations = get_school_health_recommendations(school, user=request.user)
        status = (health.get("status") or "").strip()
        if status == "setup_needed":
            misconfiguration_flags.append("setup_needed")
        elif status == "at_risk":
            misconfiguration_flags.append("at_risk")
        if int(progress.get("percent") or 0) < 50:
            misconfiguration_flags.append("low_progress")
    onboarding_playbook_api_url = ""
    try:
        onboarding_playbook_api_url = reverse("api:ai-onboarding-playbook")
    except NoReverseMatch:
        pass
    return render_siteconfig_stem(
        request,
        "onboarding",
        {
            "school": school,
            "onboarding": progress,
            "health": health,
            "health_recommendations": recommendations,
            "misconfiguration_flags": misconfiguration_flags,
            "onboarding_playbook_api_url": onboarding_playbook_api_url,
            **onboarding_activation_frame_context(),
        },
        cp_title=_("School onboarding"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Onboarding"), active=True),
        ),
    )


@login_required
def onboarding_step_detail(
    request: HttpRequest, step_key: str
) -> HttpResponse:
    """Single activation step: deep link, open action, optional mark-done."""
    school, denied = require_tenant_lifecycle_school(request)
    if denied is not None:
        return denied
    steps = get_onboarding_steps(school, user=request.user)
    step_row = next((r for r in steps if r.get("key") == step_key), None)
    if step_row is None:
        from django.http import HttpResponseNotFound

        return HttpResponseNotFound("Unknown onboarding step")
    can_mark = not step_row.get("done")
    return render_siteconfig_stem(
        request,
        "onboarding_step",
        {
            "school": school,
            "step": step_row,
            "onboarding": get_school_onboarding_progress(school, user=request.user),
            "can_mark_pending": can_mark,
        },
        cp_title=step_row.get("title") or _("Onboarding step"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Onboarding"), url=_reverse_tenant_onboarding()),
            operator_cp_breadcrumb(
                step_row.get("title") or _("Step"), active=True
            ),
        ),
    )


@login_required
@require_POST
def onboarding_step_mark_complete(request: HttpRequest) -> HttpResponse:
    school, denied = require_tenant_lifecycle_school(request)
    if denied is not None:
        return denied
    step_key = (request.POST.get("step_key") or "").strip()
    if not step_key:
        messages.error(request, _("Missing step."))
        return HttpResponseRedirect(_reverse_tenant_onboarding())
    try:
        mark_school_onboarding_step_complete(school, step_key)
    except ValueError as e:
        if str(e) == "unknown_onboarding_step":
            messages.error(request, _("Not a valid activation step."))
        else:
            messages.error(str(e))
        return HttpResponseRedirect(_reverse_tenant_onboarding())
    messages.success(
        request,
        _("Step marked complete. Progress has been updated."),
    )
    return HttpResponseRedirect(_reverse_tenant_onboarding())
