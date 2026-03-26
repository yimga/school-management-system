"""
Named URL presets for FleetGovernedChange.apply_surface_url (platform admin).

Resolves Django URL names the same way operator outcomes do: try manager urlconf
first (``super:`` routes), then the process default ROOT_URLCONF (``studio_os:``, etc.).
"""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse

# (url_name, short label) — values must reverse in tests or at runtime.
FLEET_APPLY_SURFACE_PRESETS: tuple[tuple[str, str], ...] = (
    ("super:package_rollout", "Package rollout"),
    ("studio_os:automation_staged_activation", "Staged activation"),
    ("studio_os:rollback", "Rollback (Control)"),
    ("studio_os:control_impact", "Diff / impact summary"),
    ("siteconfig:feature_control_panel", "Feature control"),
    ("siteconfig:feature_control_audit", "Feature audit"),
    ("super:marketplace_governance", "Marketplace governance"),
    ("super:runtime_inspector", "Runtime inspector"),
    ("super:app_catalog", "App catalog"),
)


def fleet_apply_surface_preset_choices() -> tuple[tuple[str, str], ...]:
    """Blank-first choices tuple for ModelForms."""
    return ("", "— Manual path only —"), *FLEET_APPLY_SURFACE_PRESETS


def resolve_fleet_apply_surface(url_name: str) -> str | None:
    """Return path (starting with /) or None if the name does not reverse."""
    name = (url_name or "").strip()
    if not name:
        return None
    for urlconf in ("config.manager_urls", None):
        try:
            if urlconf is not None:
                return reverse(name, urlconf=urlconf)
            return reverse(name)
        except NoReverseMatch:
            continue
    return None
