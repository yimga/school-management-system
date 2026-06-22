"""Admin 'set school default' surface for the shared table-intelligence engine.

Sibling of ``views_command_palette`` / ``views_sidebar`` — same isolated,
no-migration pattern. The engine (``static/js/rmc-table-intelligence.js``) reads
payload-backed runtime defaults off the SITE façade (emitted in the
``#rmc-tables-config`` island) and auto-attaches to every ``table.rmc-data-table``.
This view lets a tenant admin set those school defaults; each user still gets
per-user density + hidden-column prefs layered on top, locally.

Writes via ``set_runtime_default`` (whitelisted in ``_WIZARD_RUNTIME_DEFAULT_KEYS``;
lands in ``school.settings["runtime_defaults"]`` and reads back through the
``table_`` prefix owner — no migration).
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_BOOL_KEYS = ("table_intelligence", "table_filter", "table_sort", "table_columns", "table_export")
_DENSITIES = ("compact", "comfortable", "spacious")


def _can_manage_tables(user) -> bool:
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
def table_settings_view(request):
    """Tenant-admin surface to set the SCHOOL DEFAULTS for the table engine."""
    from apps.platform_runtime.helpers import get_effective_site_settings

    school = getattr(request, "school", None)
    can_manage = _can_manage_tables(request.user)

    if request.method == "POST":
        if not can_manage:
            return HttpResponseForbidden(_("You don't have permission to change table defaults."))
        if school is None:
            messages.error(request, _("No school context — open this from a tenant workspace."))
            return redirect("siteconfig:table_settings")
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        for key in _BOOL_KEYS:
            set_runtime_default(school=school, field=key, value=(request.POST.get(key) == "on"))
        density = (request.POST.get("table_density") or "comfortable").strip().lower()
        if density not in _DENSITIES:
            density = "comfortable"
        set_runtime_default(school=school, field="table_density", value=density)
        messages.success(request, _("Table defaults saved for this school."))
        return redirect("siteconfig:table_settings")

    site = get_effective_site_settings(request=request)
    ctx = {
        "can_manage": can_manage,
        "table_intelligence": _bool_default_on(site, "table_intelligence"),
        "table_filter": _bool_default_on(site, "table_filter"),
        "table_sort": _bool_default_on(site, "table_sort"),
        "table_columns": _bool_default_on(site, "table_columns"),
        "table_export": _bool_default_on(site, "table_export"),
        "table_density": getattr(site, "table_density", None) or "comfortable",
        "density_choices": _DENSITIES,
    }
    return render(request, "siteconfig/table_settings.html", ctx)
