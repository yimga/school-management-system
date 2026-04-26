# -*- coding: utf-8 -*-
"""Read-only school activation checklist (CP; evidence-style)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.accounts.decorators import permission_required
from apps.platform_runtime.customer_health import (
    calculate_school_health,
    get_school_health_recommendations,
)
from apps.platform_runtime.onboarding import get_school_onboarding_progress


@login_required
@permission_required("settings.manage", raise_exception=True)
def school_activation_onboarding(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    progress: dict = {}
    health: dict = {}
    recommendations: list = []
    if school is not None:
        progress = get_school_onboarding_progress(school, user=request.user)
        health = calculate_school_health(school)
        recommendations = get_school_health_recommendations(school, user=request.user)
    return render(
        request,
        "siteconfig/onboarding.html",
        {
            "school": school,
            "onboarding": progress,
            "health": health,
            "health_recommendations": recommendations,
        },
    )
