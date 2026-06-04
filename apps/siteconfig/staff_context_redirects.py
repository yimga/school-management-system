"""Safe redirects when tenant-scoped siteconfig views lack request.school."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse

from apps.schools.control_plane import is_control_plane_request


def redirect_staff_without_school(
    request,
    *,
    message: str = "",
    embed_aware: bool = False,
):
    """
    Manager host has no tenant school; portal:* is not in manager urlconf.
    Send operators to Theme & Experience (embed) or /super/ instead of crashing.
    """
    if message:
        messages.warning(request, message)

    if is_control_plane_request(request):
        wants_embed = embed_aware and (request.GET.get("embed") or "").strip() in (
            "1",
            "true",
            "yes",
        )
        candidates: list[tuple[str, str]] = []
        if wants_embed:
            candidates.append(("siteconfig:theme_colors", "embed=1"))
        candidates.extend(
            [
                ("studio_os:experience", ""),
                ("siteconfig:theme_colors", "standalone=1"),
                ("super:dashboard", ""),
            ]
        )
        for name, query in candidates:
            try:
                url = reverse(name)
                if query:
                    url += ("&" if "?" in url else "?") + query
                return redirect(url)
            except NoReverseMatch:
                continue
        return redirect("/super/")

    for name in ("portal:home", "siteconfig:user_preferences"):
        try:
            return redirect(name)
        except NoReverseMatch:
            continue
    return redirect("/")
