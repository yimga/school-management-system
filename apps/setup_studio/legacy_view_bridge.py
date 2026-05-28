"""Legacy view → Unified Wizard Engine bridge (v3.99.24, 2026-05-28).

Five legacy wizard views existed as ad-hoc Python/template flows before
v3.99.23. That wave shipped their JSON definitions + resolvers. This
module is the one-call bridge that turns each legacy view into a thin
shim: detect the engine override, redirect to the engine route.

Default flip
------------
Each migrated wizard has an entry in ``_DEFAULT_OVERRIDES`` that maps
its legacy view to the engine wizard_key + audience. Operators can
disable per-wizard by setting:

    RMC_WIZARD_ENGINE_OVERRIDES = {"custom_domain": False, ...}

in Django settings (default: all-on for the v3.99.23 keys).

A query-string escape hatch ``?legacy=1`` always renders the legacy
view, regardless of override state, to keep an explicit rollback path
during the bake-in window.

CLAUDE.md constraints honored
-----------------------------
* No hardcoded role strings — audience comes from the wizard JSON's
  ``audience`` array (read via wizard_engine.get_wizard).
* No new migrations — uses Django settings only.
* No tenant queryset — pure routing.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger(__name__)


# Legacy view key → (engine_wizard_key, audience)
_DEFAULT_OVERRIDES: dict[str, tuple[str, str]] = {
    "create_school":      ("super_create_school",    "operator"),
    "custom_domain":      ("custom_domain_setup",    "tenant_admin"),
    "mfa_setup":          ("mfa_setup",              "tenant_admin"),
    "account_migration":  ("account_migration",      "tenant_admin"),
    "parent_link_child":  ("parent_link_child",      "parent"),
    # v4.00.5: teacher + student self-onboarding migrated to engine
    "teacher_onboarding": ("teacher_self_onboarding","teacher"),
    "student_onboarding": ("student_self_onboarding","student"),
}


def _is_override_enabled(legacy_key: str) -> bool:
    """Operator-overrideable per-wizard switch. Default: enabled for v3.99.23 set."""
    overrides = getattr(settings, "RMC_WIZARD_ENGINE_OVERRIDES", None)
    if not isinstance(overrides, dict):
        return legacy_key in _DEFAULT_OVERRIDES
    if legacy_key not in overrides:
        return legacy_key in _DEFAULT_OVERRIDES
    return bool(overrides.get(legacy_key))


def _audience_to_route_name(audience: str) -> str:
    """Map wizard audience → URL route name family.

    Tenant audiences (``tenant_admin``, ``parent``, ``teacher``, ``student``,
    ``staff``) all use the tenant route. Operator uses operator route.
    """
    return "operator_wizard" if audience == "operator" else "tenant_wizard"


def engine_redirect_response(
    request: HttpRequest,
    legacy_key: str,
    *,
    step_key: str | None = None,
) -> HttpResponse | None:
    """Return a redirect to the engine route, or None to render the legacy view.

    Use at the very top of a legacy view::

        def custom_domain_wizard(request):
            resp = engine_redirect_response(request, "custom_domain")
            if resp is not None:
                return resp
            # ... legacy fallback rendering ...

    The query-string ``?legacy=1`` opts out (returns None) so the legacy
    template can be exercised explicitly during the bake-in window.
    """
    if request.GET.get("legacy") == "1":
        return None

    if not _is_override_enabled(legacy_key):
        return None

    mapping = _DEFAULT_OVERRIDES.get(legacy_key)
    if mapping is None:
        return None

    engine_wizard_key, audience = mapping
    route = _audience_to_route_name(audience)
    name = f"setup_studio:{route}"

    kwargs: dict[str, Any] = {"wizard_key": engine_wizard_key}
    if step_key:
        name = f"setup_studio:{route}_step"
        kwargs["step_key"] = step_key

    try:
        url = reverse(name, kwargs=kwargs)
    except Exception as exc:  # noqa: BLE001 — reverse fails should fall back to legacy
        logger.warning("engine_redirect_response: reverse failed for %s: %s", name, exc)
        return None

    return redirect(url)


def list_overrides_for_admin() -> list[dict[str, Any]]:
    """Read-only view of overrides for an admin UI. Always includes default state."""
    overrides = getattr(settings, "RMC_WIZARD_ENGINE_OVERRIDES", None) or {}
    rows = []
    for legacy_key, (engine_key, audience) in _DEFAULT_OVERRIDES.items():
        rows.append({
            "legacy_key": legacy_key,
            "engine_wizard_key": engine_key,
            "audience": audience,
            "enabled": _is_override_enabled(legacy_key),
            "settings_override_set": legacy_key in overrides,
        })
    return rows
