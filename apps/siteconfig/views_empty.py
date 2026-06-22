"""Empty-state intelligence settings: the SCHOOL DEFAULTS for the shared engine.

The two table empty states (rmc-table-intelligence.js) + ad-hoc adoption
(rmc-empty-intelligence.js) read their switches from the #rmc-empty-config
island (SITE cascade, default-on); the first-run progress nudge reads
SITE.empty_first_run server-side. This view lets a tenant admin flip those
switches for the whole school, mirroring the sidebar / table / palette /
dashboard / form settings pattern. Payload-backed cascade — no migration.
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

_BOOL_KEYS = (
    "empty_intelligence",
    "empty_table_filter",
    "empty_table_data",
    "empty_adopt",
    "empty_first_run",
)


def _can_manage_empty(user) -> bool:
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
def empty_settings_view(request):
    """Tenant-admin surface to set the SCHOOL DEFAULTS for the empty-state engine."""
    from apps.platform_runtime.helpers import get_effective_site_settings

    school = getattr(request, "school", None)
    can_manage = _can_manage_empty(request.user)

    if request.method == "POST":
        if not can_manage:
            return HttpResponseForbidden(_("You don't have permission to change empty-state defaults."))
        if school is None:
            messages.error(request, _("No school context — open this from a tenant workspace."))
            return redirect("siteconfig:empty_settings")
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        for key in _BOOL_KEYS:
            set_runtime_default(school=school, field=key, value=(request.POST.get(key) == "on"))
        messages.success(request, _("Empty-state defaults saved for this school."))
        return redirect("siteconfig:empty_settings")

    site = get_effective_site_settings(request=request)
    ctx = {
        "can_manage": can_manage,
        "empty_intelligence": _bool_default_on(site, "empty_intelligence"),
        "empty_table_filter": _bool_default_on(site, "empty_table_filter"),
        "empty_table_data": _bool_default_on(site, "empty_table_data"),
        "empty_adopt": _bool_default_on(site, "empty_adopt"),
        "empty_first_run": _bool_default_on(site, "empty_first_run"),
    }
    return render(request, "siteconfig/empty_settings.html", ctx)
