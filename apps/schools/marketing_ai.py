"""
Marketing AI integration point (Phase 10 — 7.1).
Category-grade AI visuals: hero images/videos, migration/setup/ecosystem visuals.
Asset governance: proof_hero_image_key, style tokens, versioning/approval.
When AI-generated assets are shipped, plug them in here; templates already consume
proof_hero_image_key and hero/asset URLs from marketing_views context.
"""

from __future__ import annotations

from django.conf import settings


# Asset keys for governance (style guide, versioning, approval). Phase 10: placeholders.
MARKETING_AI_ASSET_KEYS = (
    "hero_dashboard",
    "hero_video",
    "hero_migration_flow",
    "hero_setup_studio",
    "hero_ecosystem",
    "hero_marketplace",
)


def get_marketing_ai_asset_url(key: str) -> str | None:
    """
    Resolve URL for an AI-generated or governed marketing asset.
    Phase 10: returns settings override or None (caller uses static/placeholder).
    When 7.1 ships: can call external AI asset service or lookup from MarketingContent/asset store.
    """
    if key not in MARKETING_AI_ASSET_KEYS:
        return None
    setting_map = {
        "hero_dashboard": getattr(settings, "MARKETING_HERO_IMAGE_URL", None),
        "hero_video": getattr(settings, "MARKETING_HERO_VIDEO_URL", None),
        "hero_migration_flow": getattr(
            settings, "MARKETING_MIGRATION_FLOW_IMAGE_URL", None
        ),
        "hero_setup_studio": getattr(
            settings, "MARKETING_SETUP_STUDIO_IMAGE_URL", None
        ),
        "hero_ecosystem": getattr(settings, "MARKETING_ECOSYSTEM_IMAGE_URL", None),
        "hero_marketplace": getattr(settings, "MARKETING_MARKETPLACE_IMAGE_URL", None),
    }
    return setting_map.get(key)
