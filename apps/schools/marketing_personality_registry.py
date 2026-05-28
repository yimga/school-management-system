"""Context-aware marketing personality pages (MULTI-PERSONALITY-GRID)."""

from __future__ import annotations

from typing import Any

# slug → page spec (template path relative to templates/)
PERSONALITY_PAGES: dict[str, dict[str, Any]] = {
    "homepage": {
        "template": "marketing/homepage.html",
        "title_token": "txt_hero_headline",
        "personality": "sovereign",
        "scroll_policy": "viewport-lock",
    },
    "academics": {
        "template": "marketing/academics.html",
        "title_token": "txt_academics_headline",
        "personality": "fluid",
        "scroll_policy": "viewport-lock",
        "scripts": ("mkt-gradebook-morph.js",),
    },
    "edge-mesh": {
        "template": "marketing/edge_mesh.html",
        "title_token": "txt_edge_headline",
        "personality": "rugged",
        "scroll_policy": "viewport-lock",
        "scripts": ("mkt-network-state.js",),
    },
    "compliance": {
        "template": "marketing/compliance.html",
        "title_token": "txt_compliance_headline",
        "personality": "governance",
        "scroll_policy": "viewport-lock",
    },
    "pricing": {
        "template": "marketing/pricing.html",
        "title_token": "txt_pricing_headline",
        "personality": "clinical",
        "scroll_policy": "viewport-lock",
        "scripts": ("mkt-entitlement-calculator.js", "mkt-split-ledger.js"),
    },
}


def get_personality_page(slug: str) -> dict[str, Any] | None:
    key = (slug or "").strip().lower()
    return PERSONALITY_PAGES.get(key)


def personality_slugs() -> tuple[str, ...]:
    return tuple(PERSONALITY_PAGES.keys())
