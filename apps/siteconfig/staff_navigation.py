"""
Staff-facing Site Settings URLs: manager host uses /super/ control plane; tenant host uses Django admin.
Single resolver so we never dead-link after platform admin unregisters SiteSettings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import NoReverseMatch, reverse

if TYPE_CHECKING:
    from django.http import HttpRequest


def is_manager_control_plane(request: HttpRequest | None) -> bool:
    return getattr(request, "public_host_kind", None) == "manager"


def site_settings_list_url(request: HttpRequest | None = None) -> str | None:
    if request is not None and is_manager_control_plane(request):
        try:
            return reverse("super:site_settings_list")
        except NoReverseMatch:
            return None
    try:
        return reverse("admin:siteconfig_sitesettings_changelist")
    except NoReverseMatch:
        pass
    # Platform URLConf: SiteSettings is not on platform admin — use control plane.
    try:
        return reverse("super:site_settings_list")
    except NoReverseMatch:
        return None


def site_settings_change_url(
    request: HttpRequest | None, pk: int | None
) -> str | None:
    if pk is None:
        return site_settings_list_url(request)
    if request is not None and is_manager_control_plane(request):
        try:
            return reverse("super:site_settings_edit", kwargs={"pk": int(pk)})
        except (NoReverseMatch, TypeError, ValueError):
            return None
    try:
        return reverse("admin:siteconfig_sitesettings_change", args=[int(pk)])
    except (NoReverseMatch, TypeError, ValueError):
        pass
    try:
        return reverse("super:site_settings_edit", kwargs={"pk": int(pk)})
    except (NoReverseMatch, TypeError, ValueError):
        return None
