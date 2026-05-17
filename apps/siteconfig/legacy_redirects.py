"""
Legacy siteconfig URL redirects (bookmarks, admin paths, Studio deep links).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse

from apps.schools.control_plane import use_control_plane_shell


def legacy_customizer_redirect(request: HttpRequest) -> HttpResponse:
    """
    /siteconfig/customizer/ — manager/local → Theme & Experience (CP shell);
    tenant → Studio OS Experience (canonical studio surface).
    """
    if use_control_plane_shell(request):
        params = request.GET.copy()
        params.setdefault("standalone", "1")
        try:
            base = reverse("siteconfig:theme_colors")
        except NoReverseMatch:
            base = "/siteconfig/theme-colors/"
        query = params.urlencode()
        return redirect(f"{base}?{query}" if query else base)
    try:
        base = reverse("studio_os:experience")
    except NoReverseMatch:
        base = "/studio/experience/"
    qs = request.META.get("QUERY_STRING", "")
    return redirect(f"{base}?{qs}" if qs else base)


def legacy_customizer_clear_preview_redirect(request: HttpRequest) -> HttpResponse:
    """Legacy ``/siteconfig/customizer/clear-preview/`` → canonical preview clear."""
    qs = request.META.get("QUERY_STRING", "")
    try:
        base = reverse("siteconfig:clear_preview")
    except NoReverseMatch:
        base = "/siteconfig/preview/clear/"
    return redirect(f"{base}?{qs}" if qs else base)
