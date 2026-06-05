"""
Cockpit shell configuration — Single Source of Truth (v8 200x app-shell).

Everything the platform-wide cockpit chrome renders (header composition, the
LIVE ticker, the emoji primary-nav glyphs, the per-surface dark/light skin, the
page-header Export-PDF / Quick-action buttons, the co-pilot rail) is driven by
the values in this module. Nothing is hardcoded in the templates: each knob is a
``cockpit_*`` virtual key that rides the existing brand_experience cascade.

Cascade integration (no migration required):
  * ``apps.siteconfig.domain_ownership.PREFIX_FIELD_OWNERS`` maps the ``cockpit_``
    prefix to ``brand_experience`` so ``is_runtime_payload_shadow_key("cockpit_*")``
    is True. That makes ``SITE.cockpit_<key>`` resolve through
    ``SiteSettings.__getattr__`` → ``RuntimeDefaults.payload`` (global default)
    or the per-tenant ``school.settings["runtime_defaults"]`` overlay.
  * When a key is absent, ``virtual_site_setting_default`` defers to
    :func:`cockpit_setting_default` here, so every knob has a sane platform default.
  * Admins change any value through the brand_experience-owned config UI; the
    value lands in payload and is read back transparently.

So the resolution order for any knob is, highest-priority first:
  per-tenant override  →  global RuntimeDefaults payload  →  this module's default.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Surfaces — each shell the cockpit chrome can render on.
# ---------------------------------------------------------------------------
SURFACE_MANAGER = "manager"  # manager.runmycampus.com control plane (operator)
SURFACE_BACKEND = "backend"  # tenant school admin / backoffice (staff)
SURFACE_TEACHER = "teacher"
SURFACE_PARENT = "parent"
SURFACE_STUDENT = "student"
SURFACE_STUDIO = "studio"  # studio_os builder
SURFACE_PORTAL = "portal"  # generic authenticated tenant portal landing

COCKPIT_SURFACES: tuple[str, ...] = (
    SURFACE_MANAGER,
    SURFACE_BACKEND,
    SURFACE_TEACHER,
    SURFACE_PARENT,
    SURFACE_STUDENT,
    SURFACE_STUDIO,
    SURFACE_PORTAL,
)

# Valid skin values. "auto" defers to the user's resolved theme preference
# (handled by the existing theme bootstrap + [data-resolved-theme]).
SKIN_DARK = "dark"
SKIN_LIGHT = "light"
SKIN_AUTO = "auto"
COCKPIT_SKINS: tuple[str, ...] = (SKIN_DARK, SKIN_LIGHT, SKIN_AUTO)

# Recommendation shipped as the default: dark frame for staff/operator surfaces,
# light brand-forward frame for family-facing surfaces (parent/student). The
# tenant brand always wins via the *accent* regardless of frame tone. Each is a
# per-tenant-overridable knob, so a school can flip any surface.
#
# DEFAULTS NOTE: only the MANAGER control plane defaults to dark (it has always
# been dark, and its chrome is the verified .rmc-app-shell). Every tenant-rendered
# surface defaults to LIGHT so enabling the cockpit skin platform-wide is a no-op
# for existing tenant portals (brand-wins stays intact). The dark tenant skin is
# fully built (see rmc-cockpit-skin-v8.css [data-cockpit-skin="dark"] .tp-header)
# and one admin toggle away per surface in the Cockpit Shell settings — flip a
# staff surface (backend/teacher/studio) to dark once it's been eyeballed.
_DEFAULT_SKIN_BY_SURFACE: dict[str, str] = {
    SURFACE_MANAGER: SKIN_DARK,
    SURFACE_BACKEND: SKIN_LIGHT,
    SURFACE_TEACHER: SKIN_LIGHT,
    SURFACE_STUDIO: SKIN_LIGHT,
    SURFACE_PORTAL: SKIN_LIGHT,
    SURFACE_PARENT: SKIN_LIGHT,
    SURFACE_STUDENT: SKIN_LIGHT,
}

# Default surface-appropriate brand pill label (blank → derived elsewhere).
_DEFAULT_BRAND_PILL_BY_SURFACE: dict[str, str] = {
    SURFACE_MANAGER: "MANAGER",
    SURFACE_BACKEND: "ADMIN",  # role-string-allow: cockpit-brand-pill-display-label (not a role grant)
    SURFACE_TEACHER: "TEACHER",  # role-string-allow: cockpit-brand-pill-display-label (not a role grant)
    SURFACE_PARENT: "FAMILY",
    SURFACE_STUDENT: "STUDENT",  # role-string-allow: cockpit-brand-pill-display-label (not a role grant)
    SURFACE_STUDIO: "STUDIO",
    SURFACE_PORTAL: "PORTAL",
}

# ---------------------------------------------------------------------------
# Primary-nav emoji glyphs (the v8 HTML mapping). Keyed by the nav item id
# produced by ``build_primary_control_plane_nav``. Overridable per-tenant via
# the ``cockpit_nav_glyphs`` knob (a partial map merges over these).
# ---------------------------------------------------------------------------
DEFAULT_COCKPIT_NAV_GLYPHS: dict[str, str] = {
    "primary_home": "🏠",
    "primary_studio": "⎈",
    "primary_operations": "⚡",
    "primary_marketplace": "🛒",
    "primary_analytics": "📈",
    "primary_migration": "☁",
    "primary_support": "🎧",
    "primary_control": "🛡",
}

# ---------------------------------------------------------------------------
# The knob registry: cockpit_* virtual key → platform default.
# This is the SOT consulted by ``virtual_site_setting_default`` and by the
# blueprint builder. Per-surface skin keys are generated from the map above.
# ---------------------------------------------------------------------------
COCKPIT_DEFAULTS: dict[str, Any] = {
    # Header composition toggles
    "cockpit_search_enabled": True,
    "cockpit_live_ticker_enabled": True,
    "cockpit_presence_enabled": True,
    "cockpit_copilot_rail_enabled": True,
    "cockpit_show_config_chip": True,
    "cockpit_show_studio_chip": True,
    "cockpit_show_theme_toggle": True,
    "cockpit_show_bell": True,
    "cockpit_show_breadcrumb": True,
    # Brand / identity
    "cockpit_tagline": "",  # blank → falls back to SITE.tagline
    "cockpit_brand_pill_label": "",  # blank → surface-derived
    # Primary nav
    "cockpit_nav_use_glyphs": True,  # emoji glyphs vs Bootstrap icons
    "cockpit_nav_glyphs": {},  # partial override map, merges over defaults
    "cockpit_nav_hidden_ids": [],  # nav ids to hide
    # Page-header actions
    "cockpit_export_pdf_enabled": True,
    "cockpit_quick_action_enabled": True,
    "cockpit_quick_action_mode": "command_palette",  # or "menu"
    # LIVE ticker behaviour
    "cockpit_ticker_speed_seconds": 60,
    "cockpit_ticker_max_events": 12,
}


def _skin_key(surface: str) -> str:
    return f"cockpit_skin_{surface}"


def is_cockpit_key(name: str) -> bool:
    """True for any ``cockpit_*`` virtual setting key (knob or per-surface skin)."""
    return isinstance(name, str) and name.startswith("cockpit_")


def cockpit_setting_default(name: str) -> Any:
    """Platform default for a ``cockpit_*`` virtual key.

    Consulted by ``apps.siteconfig.models_support.virtual_site_setting_default``
    so ``SITE.cockpit_<key>`` never returns an unusable null. Returns ``None``
    for unrecognised cockpit keys (forward-compatible — templates use ``|default``).
    """
    if not is_cockpit_key(name):
        return None
    # Per-surface skin keys: cockpit_skin_<surface>
    if name.startswith("cockpit_skin_"):
        surface = name[len("cockpit_skin_") :]
        return _DEFAULT_SKIN_BY_SURFACE.get(surface, SKIN_DARK)
    return COCKPIT_DEFAULTS.get(name)


def normalize_skin(value: Any, *, surface: str) -> str:
    """Coerce a stored skin value into a valid skin, falling back to the
    surface default then dark."""
    candidate = str(value or "").strip().lower()
    if candidate in COCKPIT_SKINS:
        return candidate
    return _DEFAULT_SKIN_BY_SURFACE.get(surface, SKIN_DARK)


def _truthy(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _get(site: Any, key: str) -> Any:
    """Read a cockpit_* value off the SITE façade, falling back to the module
    default. Tolerates a missing/odd SITE object."""
    if site is not None:
        try:
            val = getattr(site, key)
        except (AttributeError, TypeError, ValueError):
            val = None
        if val is not None:
            return val
    return cockpit_setting_default(key)


def resolved_nav_glyphs(site: Any) -> dict[str, str]:
    """Default glyph map with any per-tenant ``cockpit_nav_glyphs`` override merged on top."""
    glyphs = dict(DEFAULT_COCKPIT_NAV_GLYPHS)
    override = _get(site, "cockpit_nav_glyphs")
    if isinstance(override, dict):
        for k, v in override.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                glyphs[k] = v
    return glyphs


def build_cockpit_blueprint(site: Any, *, surface: str) -> dict[str, Any]:
    """Assemble the fully-resolved cockpit blueprint for a template context.

    ``site`` is the SITE façade (SiteSettings); ``surface`` is one of
    :data:`COCKPIT_SURFACES`. Every value is resolved through the cascade with
    a module default fallback, so the result is always renderable.
    """
    if surface not in COCKPIT_SURFACES:
        surface = SURFACE_MANAGER

    skin = normalize_skin(_get(site, _skin_key(surface)), surface=surface)

    pill = str(_get(site, "cockpit_brand_pill_label") or "").strip()
    if not pill:
        pill = _DEFAULT_BRAND_PILL_BY_SURFACE.get(surface, "")

    tagline = str(_get(site, "cockpit_tagline") or "").strip()
    if not tagline:
        tagline = str(getattr(site, "tagline", "") or "").strip()

    try:
        ticker_speed = int(_get(site, "cockpit_ticker_speed_seconds"))
    except (TypeError, ValueError):
        ticker_speed = COCKPIT_DEFAULTS["cockpit_ticker_speed_seconds"]
    ticker_speed = max(8, min(ticker_speed, 600))

    try:
        ticker_max = int(_get(site, "cockpit_ticker_max_events"))
    except (TypeError, ValueError):
        ticker_max = COCKPIT_DEFAULTS["cockpit_ticker_max_events"]
    ticker_max = max(1, min(ticker_max, 50))

    quick_mode = str(_get(site, "cockpit_quick_action_mode") or "").strip().lower()
    if quick_mode not in {"command_palette", "menu"}:
        quick_mode = "command_palette"

    hidden_ids = _get(site, "cockpit_nav_hidden_ids")
    hidden_ids = [str(x) for x in hidden_ids] if isinstance(hidden_ids, list) else []

    return {
        "surface": surface,
        "skin": skin,  # dark | light | auto
        "tagline": tagline,
        "brand_pill": pill,
        "search_enabled": _truthy(_get(site, "cockpit_search_enabled"), True),
        "live_ticker_enabled": _truthy(_get(site, "cockpit_live_ticker_enabled"), True),
        "presence_enabled": _truthy(_get(site, "cockpit_presence_enabled"), True),
        "copilot_rail_enabled": _truthy(_get(site, "cockpit_copilot_rail_enabled"), True),
        "show": {
            "config_chip": _truthy(_get(site, "cockpit_show_config_chip"), True),
            "studio_chip": _truthy(_get(site, "cockpit_show_studio_chip"), True),
            "theme_toggle": _truthy(_get(site, "cockpit_show_theme_toggle"), True),
            "bell": _truthy(_get(site, "cockpit_show_bell"), True),
            "breadcrumb": _truthy(_get(site, "cockpit_show_breadcrumb"), True),
        },
        "nav_use_glyphs": _truthy(_get(site, "cockpit_nav_use_glyphs"), True),
        "nav_glyphs": resolved_nav_glyphs(site),
        "nav_hidden_ids": hidden_ids,
        "actions": {
            "export_pdf": _truthy(_get(site, "cockpit_export_pdf_enabled"), True),
            "quick_action": _truthy(_get(site, "cockpit_quick_action_enabled"), True),
            "quick_action_mode": quick_mode,
        },
        "ticker": {
            "speed_seconds": ticker_speed,
            "max_events": ticker_max,
        },
    }


def all_cockpit_keys() -> tuple[str, ...]:
    """Every cockpit_* key the admin UI can edit (knobs + per-surface skins)."""
    keys = list(COCKPIT_DEFAULTS.keys())
    keys.extend(_skin_key(s) for s in COCKPIT_SURFACES)
    return tuple(keys)
