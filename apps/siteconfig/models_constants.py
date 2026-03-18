"""
Shared constants for siteconfig models and models_tooling.

This module has no dependency on .models or .models_tooling so that
models_tooling can import from here without creating a circular import
with models.py.
"""

from __future__ import annotations

REPORT_CARD_TYPE_TERM = "TERM"
REPORT_CARD_TYPE_ANNUAL = "ANNUAL"

LOGO_BG_MODE_CHOICES: list[tuple[str, str]] = [
    ("none", "None (disabled)"),
    ("contain", "Contain (default)"),
    ("cover", "Cover"),
    ("tile", "Tile/Repeat"),
    ("center", "Center (no scale)"),
]

BACKEND_CONSOLE_THEME_CHOICES: list[tuple[str, str]] = [
    ("dark", "Dark (slate grey)"),
    ("light", "Light (lavender tint)"),
    ("system", "System (follows OS)"),
    ("black", "Black (true black #000)"),
    ("ink", "Ink (deep black #030712)"),
    ("onyx", "Onyx (rich black #0c0c0c)"),
    ("charcoal", "Charcoal (soft black)"),
    ("graphite", "Graphite (zinc grey)"),
    ("midnight", "Midnight (deep blue-black)"),
    ("ocean", "Ocean (dark blue)"),
    ("steel", "Steel (blue-grey)"),
    ("slate", "Slate (medium grey)"),
    ("forest", "Forest (dark green)"),
    ("indigo", "Indigo (dark purple)"),
    ("amber", "Amber (warm dark)"),
    ("sand", "Sand (warm light)"),
    ("snow", "Snow (cool light)"),
    ("cream", "Cream (ivory light)"),
    ("lavender", "Lavender (soft purple light)"),
]
