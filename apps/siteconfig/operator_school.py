"""Operator school context helpers for manager-host siteconfig views."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

from apps.schools.control_plane import use_control_plane_shell


def redirect_missing_operator_school(
    request: HttpRequest,
    *,
    detail: str | None = None,
) -> HttpResponse:
    """
    Tenant: school backend. Manager / local CP: super dashboard (not tenant backend).
    """
    messages.warning(
        request,
        detail
        or _(
            "No school context. Open a school from the control plane, then return to this page."
        ),
    )
    if use_control_plane_shell(request):
        for name in ("super:dashboard", "siteconfig:console_domains_hub"):
            try:
                return redirect(reverse(name))
            except NoReverseMatch:
                continue
        return redirect("/super/")
    return redirect(reverse("accounts:backend_dashboard"))
