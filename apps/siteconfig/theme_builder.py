"""Shopify-grade theme builder — block catalog + layout validation."""

from __future__ import annotations

from typing import Any

DEFAULT_THEME_BUILDER_BLOCKS: list[dict[str, Any]] = [
    {"id": "sidebar", "type": "sidebar", "label": "Navigation sidebar", "enabled": True},
    {"id": "hero", "type": "hero", "label": "Hero header", "enabled": True},
    {"id": "metrics", "type": "metrics", "label": "Metric cards", "enabled": True},
    {"id": "chart", "type": "chart", "label": "Activity chart", "enabled": True},
    {"id": "announcement", "type": "announcement", "label": "Announcement bar", "enabled": True},
    {"id": "cta", "type": "cta", "label": "Call to action", "enabled": True},
    {"id": "footer", "type": "footer", "label": "Footer strip", "enabled": False},
]

TOKEN_FIELD_NAMES = ("primary_color", "accent_color", "header_bg_color", "footer_bg_color")

OPERATOR_RUNTIME_PAYLOAD_KEY = "operator_theme_builder_layout"
TENANT_SCHOOL_SETTINGS_KEY = "tenant_theme_builder_layout"
LEGACY_RUNTIME_PAYLOAD_KEY = "theme_builder_layout"
# Back-compat alias for tests and external references predating dual-plane split.
RUNTIME_PAYLOAD_KEY = LEGACY_RUNTIME_PAYLOAD_KEY


def default_layout() -> dict[str, Any]:
    return {
        "version": 1,
        "surface": "light",
        "blocks": [dict(b) for b in DEFAULT_THEME_BUILDER_BLOCKS],
    }


def normalize_layout(raw: Any) -> dict[str, Any]:
    """Coerce posted JSON into a stable layout dict."""
    base = default_layout()
    if not isinstance(raw, dict):
        return base
    blocks_in = raw.get("blocks")
    if isinstance(blocks_in, list) and blocks_in:
        cleaned: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in blocks_in:
            if not isinstance(item, dict):
                continue
            block_id = str(item.get("id") or item.get("type") or "").strip()
            block_type = str(item.get("type") or block_id or "section").strip()
            if not block_id or block_id in seen:
                continue
            seen.add(block_id)
            cleaned.append(
                {
                    "id": block_id,
                    "type": block_type,
                    "label": str(item.get("label") or block_type).strip()[:80],
                    "enabled": bool(item.get("enabled", True)),
                }
            )
        if cleaned:
            base["blocks"] = cleaned
    surface = str(raw.get("surface") or "light").strip().lower()
    if surface in ("light", "dark"):
        base["surface"] = surface
    version = raw.get("version")
    if isinstance(version, int) and version > 0:
        base["version"] = version
    return base
