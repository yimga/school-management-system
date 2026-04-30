"""
Guided configuration workflows — modular domain status without exposing ORM singletons.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.siteconfig.config_service import build_guided_configuration_cards


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def guided_configuration_workflows(request: HttpRequest) -> HttpResponse:
    cards = build_guided_configuration_cards(request)
    runtime_hub_url = None
    feature_control_url = None
    try:
        runtime_hub_url = reverse("siteconfig:tenant_runtime_configuration_hub")
    except NoReverseMatch:
        pass
    try:
        feature_control_url = reverse("siteconfig:feature_control_panel")
    except NoReverseMatch:
        pass
    return render(
        request,
        "siteconfig/guided_configuration_workflows.html",
        {
            "guided_cards": cards,
            "runtime_hub_url": runtime_hub_url,
            "feature_control_url": feature_control_url,
        },
    )
