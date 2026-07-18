"""Emit ThemePack.palette.admin_dashboard as live --admin-* CSS custom properties.

The seeder writes a full admin_dashboard JSON object onto ThemePack.palette.
Until this emitter runs, those keys are dead — shells only read scalar
primary_color / accent_color. This module is the single reader that turns the
JSON into CSS tokens consumed by admin + backend shells.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

# JSON key -> CSS custom property (and optional aliases).
_ADMIN_DASHBOARD_TOKEN_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("primary", ("--admin-primary", "--brand-primary", "--school-primary")),
    ("accent", ("--admin-accent", "--brand-accent", "--school-accent")),
    ("accent_light", ("--admin-accent-light",)),
    ("dashboard_bg", ("--admin-dashboard-bg",)),
    ("surface", ("--admin-surface",)),
    ("border", ("--admin-border",)),
    ("border_strong", ("--admin-border-strong",)),
    ("border_hover", ("--admin-border-hover",)),
    ("text", ("--admin-text",)),
    ("muted", ("--admin-muted",)),
    ("subtle", ("--admin-subtle",)),
    ("role_admin", ("--admin-role-admin",)),
    ("role_student", ("--admin-role-student",)),
    ("role_teacher", ("--admin-role-teacher",)),
    ("success", ("--admin-success", "--brand-success")),
    ("warning", ("--admin-warning", "--brand-warning")),
    ("danger", ("--admin-danger", "--brand-danger")),
    ("info", ("--admin-info",)),
    ("shadow", ("--admin-shadow",)),
    ("shadow_hover", ("--admin-shadow-hover",)),
    ("weather_bg", ("--admin-weather-bg",)),
)

# Reject anything that could break out of a CSS custom-property value.
_UNSAFE = re.compile(r"[;{}]|/\*|url\s*\(|expression\s*\(|@import", re.IGNORECASE)
_COLORISH = re.compile(
    r"^("
    r"#[0-9a-fA-F]{3,8}"
    r"|rgba?\([^)]{1,80}\)"
    r"|hsla?\([^)]{1,80}\)"
    r"|[a-zA-Z]{3,20}"
    r")$",
)
_SHADOWISH = re.compile(
    r"^("
    r"(?:inset\s+)?"
    r"-?\d+(?:\.\d+)?(?:px|rem|em)?(?:\s+-?\d+(?:\.\d+)?(?:px|rem|em)?){0,3}"
    r"(?:\s+(?:#[0-9a-fA-F]{3,8}|rgba?\([^)]{1,80}\)|hsla?\([^)]{1,80}\)|[a-zA-Z]{3,20}))?"
    r"(?:\s*,\s*(?:inset\s+)?"
    r"-?\d+(?:\.\d+)?(?:px|rem|em)?(?:\s+-?\d+(?:\.\d+)?(?:px|rem|em)?){0,3}"
    r"(?:\s+(?:#[0-9a-fA-F]{3,8}|rgba?\([^)]{1,80}\)|hsla?\([^)]{1,80}\)|[a-zA-Z]{3,20}))?"
    r")*"
    r")$",
)


def _sanitize_css_value(raw: Any, *, allow_shadow: bool = False) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or len(value) > 120 or _UNSAFE.search(value):
        return None
    if allow_shadow and _SHADOWISH.match(value):
        return value
    if _COLORISH.match(value):
        return value
    return None


def extract_admin_dashboard_palette(theme_pack) -> dict[str, Any]:
    """Return ``palette.admin_dashboard`` from a ThemePack-like object, or {}."""
    if theme_pack is None:
        return {}
    palette = getattr(theme_pack, "palette", None)
    if not isinstance(palette, dict):
        return {}
    admin = palette.get("admin_dashboard")
    return dict(admin) if isinstance(admin, dict) else {}


def admin_dashboard_palette_css_vars(
    palette: Mapping[str, Any] | None,
    *,
    as_root_block: bool = False,
) -> str:
    """Serialize admin_dashboard palette keys into CSS custom-property declarations.

    Returns either bare declarations (``--admin-surface: #fff;``) suitable for
    injecting inside an existing ``:root { … }``, or a full ``:root { … }`` block
    when ``as_root_block=True``. Empty string when nothing safe to emit.
    """
    if not palette:
        return ""
    parts: list[str] = []
    for json_key, css_names in _ADMIN_DASHBOARD_TOKEN_MAP:
        raw = palette.get(json_key)
        allow_shadow = json_key in {"shadow", "shadow_hover"}
        safe = _sanitize_css_value(raw, allow_shadow=allow_shadow)
        if not safe:
            continue
        for css_name in css_names:
            parts.append(f"{css_name}: {safe};")
    if not parts:
        return ""
    joined = " ".join(parts)
    if as_root_block:
        return f":root {{ {joined} }}"
    return joined
