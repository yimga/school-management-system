"""Form-intelligence settings: the SCHOOL DEFAULTS for the shared form engine.

The engine (``static/js/rmc-form-intelligence.js``) auto-attaches to every real
``<form method="post">`` and reads its switches from the ``#rmc-forms-config``
island (SITE cascade, default-on). This view lets a tenant admin flip those
switches for the whole school, mirroring the sidebar / table / palette /
dashboard settings pattern. Payload-backed cascade — no schema migration.
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
    "form_intelligence",
    "form_unsaved_guard",
    "form_pending",
    "form_validation",
    "form_section_nav",
)


def _can_manage_forms(user) -> bool:
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
def form_settings_view(request):
    """Tenant-admin surface to set the SCHOOL DEFAULTS for the form engine."""
    from apps.platform_runtime.helpers import get_effective_site_settings

    school = getattr(request, "school", None)
    can_manage = _can_manage_forms(request.user)

    if request.method == "POST":
        if not can_manage:
            return HttpResponseForbidden(_("You don't have permission to change form defaults."))
        if school is None:
            messages.error(request, _("No school context — open this from a tenant workspace."))
            return redirect("siteconfig:form_settings")
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        for key in _BOOL_KEYS:
            set_runtime_default(school=school, field=key, value=(request.POST.get(key) == "on"))
        messages.success(request, _("Form defaults saved for this school."))
        return redirect("siteconfig:form_settings")

    # config-resolver-allow: namespace passed to _bool_default_on helper for tri-state default-on toggle reads
    site = get_effective_site_settings(request=request)
    ctx = {
        "can_manage": can_manage,
        "form_intelligence": _bool_default_on(site, "form_intelligence"),
        "form_unsaved_guard": _bool_default_on(site, "form_unsaved_guard"),
        "form_pending": _bool_default_on(site, "form_pending"),
        "form_validation": _bool_default_on(site, "form_validation"),
        "form_section_nav": _bool_default_on(site, "form_section_nav"),
    }
    return render(request, "siteconfig/form_settings.html", ctx)
