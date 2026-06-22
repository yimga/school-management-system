"""Admin 'set school default' surface for the unified ⌘K command palette.

Sibling of ``views_sidebar.sidebar_settings_view`` — same isolated, no-migration
pattern. The engine (``static/js/rmc-command-palette.js``) reads four payload-
backed runtime defaults off the SITE façade and emits them as ``#rmc-cmdk`` data-
attributes (default-on). This view lets a tenant admin set those school defaults;
each user still gets adaptive ranking + pins layered on top, locally.

Deliberately isolated from the monolithic theme/experience form. Writes via
``set_runtime_default`` (whitelisted in ``_WIZARD_RUNTIME_DEFAULT_KEYS``; lands in
``school.settings["runtime_defaults"]`` and is read back through the
``command_palette_`` prefix owner — no migration).
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

# The four payload-backed cascade keys this surface owns (default-on booleans).
_PALETTE_KEYS = (
    "command_palette_intelligence",
    "command_palette_fuzzy",
    "command_palette_adaptive",
    "command_palette_federate_sidebar",
)


def _can_manage_command_palette(user) -> bool:
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
def command_palette_settings_view(request):
    """Tenant-admin surface to set the SCHOOL DEFAULTS for the ⌘K palette."""
    from apps.platform_runtime.helpers import get_effective_site_settings

    school = getattr(request, "school", None)
    can_manage = _can_manage_command_palette(request.user)

    if request.method == "POST":
        if not can_manage:
            return HttpResponseForbidden(_("You don't have permission to change command-palette defaults."))
        if school is None:
            messages.error(request, _("No school context — open this from a tenant workspace."))
            return redirect("siteconfig:command_palette_settings")
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        for key in _PALETTE_KEYS:
            set_runtime_default(school=school, field=key, value=(request.POST.get(key) == "on"))
        messages.success(request, _("Command-palette defaults saved for this school."))
        return redirect("siteconfig:command_palette_settings")

    site = get_effective_site_settings(request=request)
    ctx = {
        "can_manage": can_manage,
        "command_palette_intelligence": _bool_default_on(site, "command_palette_intelligence"),
        "command_palette_fuzzy": _bool_default_on(site, "command_palette_fuzzy"),
        "command_palette_adaptive": _bool_default_on(site, "command_palette_adaptive"),
        "command_palette_federate_sidebar": _bool_default_on(site, "command_palette_federate_sidebar"),
    }
    return render(request, "siteconfig/command_palette_settings.html", ctx)
