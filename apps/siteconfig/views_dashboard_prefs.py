"""Dashboard-intelligence endpoints: per-user cockpit prefs + school defaults.

Per-user reorder/hide/density preferences are SERVER-PERSISTED (durable +
cross-device) into the EXISTING ``DashboardUserPreference.dashboard_layout``
JSONField under a reserved namespace key — no schema migration. The engine
(``static/js/rmc-dashboard-intelligence.js``) GETs the saved prefs on load and
POSTs changes. The admin ``dashboard_settings_view`` sets the school defaults
(cascade), mirroring the sidebar / table / palette settings pattern.
"""
from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

# Reserved sub-key inside DashboardUserPreference.dashboard_layout so cockpit
# prefs never collide with the legacy str(widget_id) position entries.
_NS = "_rmc_cockpit_sections"
_DENSITIES = ("compact", "comfortable", "spacious")
_MAX_KEYS = 80
_MAX_KEY_LEN = 80
_BOOL_KEYS = ("dashboard_intelligence", "dashboard_reorder", "dashboard_adaptive")


def _clean_keys(seq):
    out = []
    for k in (seq or [])[:_MAX_KEYS]:
        s = str(k)[:_MAX_KEY_LEN].strip()
        if s:
            out.append(s)
    return out


@login_required
@require_http_methods(["GET", "POST"])
def dashboard_prefs_view(request):
    """GET → the caller's saved cockpit prefs for a surface; POST → persist them."""
    from apps.siteconfig.models_dashboard import DashboardUserPreference

    pref, _created = DashboardUserPreference.objects.get_or_create(user=request.user)
    layout = pref.dashboard_layout if isinstance(pref.dashboard_layout, dict) else {}
    bucket = layout.get(_NS) if isinstance(layout.get(_NS), dict) else {}

    if request.method == "GET":
        surface = (request.GET.get("surface") or "default")[:40]
        return JsonResponse({"surface": surface, "prefs": bucket.get(surface) or {}})

    try:
        data = json.loads((request.body or b"{}").decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    surface = (str(data.get("surface") or "default"))[:40]
    density = data.get("density")
    entry = {
        "order": _clean_keys(data.get("order")),
        "hidden": _clean_keys(data.get("hidden")),
        "density": density if density in _DENSITIES else "comfortable",
    }
    bucket[surface] = entry
    layout[_NS] = bucket
    pref.dashboard_layout = layout
    try:
        pref.save(update_fields=["dashboard_layout", "updated_at"])
    except Exception:  # noqa: BLE001 — a prefs save must never 500 the dashboard.
        logger.debug("dashboard_prefs_view save failed", exc_info=False)
        return JsonResponse({"ok": False}, status=200)
    return JsonResponse({"ok": True})


def _can_manage_dashboard(user) -> bool:
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
    return getattr(site, key, None) is not False


@login_required
@require_http_methods(["GET", "POST"])
def dashboard_settings_view(request):
    """Tenant-admin surface to set the SCHOOL DEFAULTS for the dashboard engine."""
    from apps.platform_runtime.helpers import get_effective_site_settings

    school = getattr(request, "school", None)
    can_manage = _can_manage_dashboard(request.user)

    if request.method == "POST":
        if not can_manage:
            return HttpResponseForbidden(_("You don't have permission to change dashboard defaults."))
        if school is None:
            messages.error(request, _("No school context — open this from a tenant workspace."))
            return redirect("siteconfig:dashboard_settings")
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        for key in _BOOL_KEYS:
            set_runtime_default(school=school, field=key, value=(request.POST.get(key) == "on"))
        density = (request.POST.get("dashboard_density") or "comfortable").strip().lower()
        if density not in _DENSITIES:
            density = "comfortable"
        set_runtime_default(school=school, field="dashboard_density", value=density)
        messages.success(request, _("Dashboard defaults saved for this school."))
        return redirect("siteconfig:dashboard_settings")

    site = get_effective_site_settings(request=request)
    ctx = {
        "can_manage": can_manage,
        "dashboard_intelligence": _bool_default_on(site, "dashboard_intelligence"),
        "dashboard_reorder": _bool_default_on(site, "dashboard_reorder"),
        "dashboard_adaptive": _bool_default_on(site, "dashboard_adaptive"),
        "dashboard_density": getattr(site, "dashboard_density", None) or "comfortable",
        "density_choices": _DENSITIES,
    }
    return render(request, "siteconfig/dashboard_settings.html", ctx)
