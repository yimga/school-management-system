"""Live sidebar-badge endpoint for the tenant portal (intelligent sidebars Phase 2).

The portal sidebar already computes pending counts (workflow / finance /
signatures) into the item dicts at render time. Rather than re-derive them here
(and risk drift), this endpoint re-runs the SAME builder and returns the badges
it produced, keyed by item id. ``rmc-sidebar-intelligence.js`` polls this and
updates the nav badges in place — so a teacher sees a new "marks pending" count
without reloading. The underlying counts are cached ~60s, so the poll is cheap.

Returns ``{"badges": {item_id: count, ...}, "interval": <seconds>}``. Fails
soft to an empty payload — a badge poll must never error the shell.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 60
_DENSITIES = ("compact", "comfortable", "spacious")


@login_required
@require_GET
def sidebar_badge_counts(request):
    badges: dict[str, int] = {}
    try:
        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_items

        site = get_effective_site_settings(request=request)
        for item in build_portal_sidebar_items(request, site) or []:
            count = item.get("badge")
            try:
                count = int(count or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0 and item.get("id"):
                badges[str(item["id"])] = count
    except Exception:  # noqa: BLE001 — a badge poll must never break; degrade to empty.
        logger.debug("sidebar_badge_counts failed", exc_info=False)
    return JsonResponse({"badges": badges, "interval": _POLL_INTERVAL_SECONDS})


def _can_manage_sidebar(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    checker = getattr(user, "has_feature_permission", None)
    try:
        return bool(checker and checker("settings.manage"))
    except Exception:  # noqa: BLE001 — permission helper must never 500 the page.
        return False


def _bool_default_on(site, key) -> bool:
    """Effective on/off for a default-on toggle: ON unless explicitly set False."""
    return getattr(site, key, None) is not False


@login_required
@require_http_methods(["GET", "POST"])
def sidebar_settings_view(request):
    """Tenant-admin surface to set the SCHOOL DEFAULTS for the intelligent
    sidebar (the per-user popover still lets each user override locally).

    Isolated from the monolithic theme/experience form on purpose. Writes the
    payload-backed runtime defaults via ``set_runtime_default`` (no migration).
    """
    from apps.platform_runtime.helpers import get_effective_site_settings

    school = getattr(request, "school", None)
    can_manage = _can_manage_sidebar(request.user)

    if request.method == "POST":
        if not can_manage:
            return HttpResponseForbidden(_("You don't have permission to change sidebar defaults."))
        if school is None:
            messages.error(request, _("No school context — open this from a tenant workspace."))
            return redirect("siteconfig:sidebar_settings")
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        density = (request.POST.get("sidebar_density") or "comfortable").strip().lower()
        if density not in _DENSITIES:
            density = "comfortable"
        updates = {
            "sidebar_intelligence": request.POST.get("sidebar_intelligence") == "on",
            "sidebar_search": request.POST.get("sidebar_search") == "on",
            "sidebar_adaptive_order": request.POST.get("sidebar_adaptive_order") == "on",
            "sidebar_density": density,
        }
        for field, value in updates.items():
            set_runtime_default(school=school, field=field, value=value)
        messages.success(request, _("Sidebar defaults saved for this school."))
        return redirect("siteconfig:sidebar_settings")

    site = get_effective_site_settings(request=request)
    ctx = {
        "can_manage": can_manage,
        "sidebar_intelligence": _bool_default_on(site, "sidebar_intelligence"),
        "sidebar_search": _bool_default_on(site, "sidebar_search"),
        "sidebar_adaptive_order": _bool_default_on(site, "sidebar_adaptive_order"),
        "sidebar_density": getattr(site, "sidebar_density", None) or "comfortable",
        "density_choices": _DENSITIES,
    }
    return render(request, "siteconfig/sidebar_settings.html", ctx)
