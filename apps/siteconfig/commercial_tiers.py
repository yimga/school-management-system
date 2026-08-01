"""
Commercial packaging tiers (Free / Pro / Enterprise) for marketplace and billing UX.

Maps ``Plan.slug`` values to a coarse tier used for minimum-tier gates in app manifests.
BR-10 technical tiers (core/interop/intelligence) remain in ``billing_sku_registry``;
this module is the GTM ladder only.
"""

from __future__ import annotations

from typing import Any, Final

COMMERCIAL_TIER_FREE: Final[str] = "free"
COMMERCIAL_TIER_PRO: Final[str] = "pro"
COMMERCIAL_TIER_ENTERPRISE: Final[str] = "enterprise"

_TIER_RANK: Final[dict[str, int]] = {
    COMMERCIAL_TIER_FREE: 0,
    COMMERCIAL_TIER_PRO: 1,
    COMMERCIAL_TIER_ENTERPRISE: 2,
}

# Includes the ACTUAL seeded plan slugs (seed_subscription_catalog.py), not just the
# generic aliases — previously every real slug (free-starter … sovereign-self-hosted)
# fell through commercial_tier_for_plan_slug() to FREE, so even the sovereign flagship
# resolved to rank-0 and was blocked from enterprise-tier marketplace packs.
_PLAN_SLUG_FREE: Final[frozenset[str]] = frozenset(
    {
        "free", "basic", "starter", "community", "trial",
        "free-starter", "ngo-low-resource",
    }
)
_PLAN_SLUG_PRO: Final[frozenset[str]] = frozenset(
    {
        "pro", "professional", "growth", "plus", "standard",
        "micro-school", "small-school", "growing-school", "professional-school",
        "developer-partner",
    }
)
_PLAN_SLUG_ENTERPRISE: Final[frozenset[str]] = frozenset(
    {
        "enterprise", "ent", "ministry", "ultimate",
        "multi-campus", "enterprise-network", "district-ministry",
        "white-label", "sovereign-self-hosted",
    }
)


def normalize_commercial_tier_slug(raw: object) -> str:
    """Return ``free``, ``pro``, ``enterprise``, or ``''`` if missing/invalid."""
    s = str(raw or "").strip().lower()
    if s in (COMMERCIAL_TIER_FREE, COMMERCIAL_TIER_PRO, COMMERCIAL_TIER_ENTERPRISE):
        return s
    return ""


def commercial_tier_for_plan_slug(plan_slug: object) -> str:
    """
    Resolve commercial tier from ``Plan.slug``.

    Unknown slugs return ``free`` at rank 0 (strict gate: use standard slugs for paid shapes).
    """
    key = str(plan_slug or "").strip().lower()
    if not key:
        return COMMERCIAL_TIER_FREE
    if key in _PLAN_SLUG_FREE:
        return COMMERCIAL_TIER_FREE
    if key in _PLAN_SLUG_PRO:
        return COMMERCIAL_TIER_PRO
    if key in _PLAN_SLUG_ENTERPRISE:
        return COMMERCIAL_TIER_ENTERPRISE
    return COMMERCIAL_TIER_FREE


def commercial_tier_rank(tier: object) -> int:
    t = normalize_commercial_tier_slug(tier)
    if not t:
        return 0
    return int(_TIER_RANK.get(t, 0))


def commercial_tier_for_school(school) -> str:
    plan = getattr(school, "plan", None) if school is not None else None
    slug = getattr(plan, "slug", "") if plan else ""
    return commercial_tier_for_plan_slug(slug)


def tier_meets_minimum(school_tier: object, required_tier: object) -> bool:
    req = normalize_commercial_tier_slug(required_tier)
    if not req:
        return True
    return commercial_tier_rank(school_tier) >= commercial_tier_rank(req)


def plan_display_context(school) -> dict[str, Any]:
    """
    Plan label + commercial tier for operator/catalog copy.

    ``tier_key`` is one of free | pro | enterprise | custom (non-mapped slug).
    """
    plan = getattr(school, "plan", None) if school is not None else None
    if plan is None:
        return {
            "slug": "",
            "name": "",
            "tier_key": "unknown",
            "tier_label": "—",
            "commercial_tier": COMMERCIAL_TIER_FREE,
        }
    slug = (getattr(plan, "slug", "") or "").strip()
    name = (getattr(plan, "name", "") or "").strip() or slug or "Plan"
    key = slug.lower()
    commercial = commercial_tier_for_plan_slug(slug)
    if key in _PLAN_SLUG_FREE:
        tier_key, tier_label = COMMERCIAL_TIER_FREE, "Free"
    elif key in _PLAN_SLUG_PRO:
        tier_key, tier_label = COMMERCIAL_TIER_PRO, "Pro"
    elif key in _PLAN_SLUG_ENTERPRISE:
        tier_key, tier_label = COMMERCIAL_TIER_ENTERPRISE, "Enterprise"
    else:
        tier_key, tier_label = "custom", name
    return {
        "slug": slug,
        "name": name,
        "tier_key": tier_key,
        "tier_label": tier_label,
        "commercial_tier": commercial,
    }


def next_commercial_tier(tier_key: object) -> str:
    """Return the next tier slug in the ladder, or ``''`` if already at top."""
    t = normalize_commercial_tier_slug(tier_key) or str(tier_key or "").strip().lower()
    if t == COMMERCIAL_TIER_FREE or t == "unknown" or t == "custom":
        return COMMERCIAL_TIER_PRO
    if t == COMMERCIAL_TIER_PRO:
        return COMMERCIAL_TIER_ENTERPRISE
    return ""


def plan_slug_candidates_for_commercial_tier(tier: object) -> frozenset[str]:
    """Return known plan slug hints for a commercial tier (for Stripe price / upgrade UX)."""
    t = normalize_commercial_tier_slug(tier)
    if t == COMMERCIAL_TIER_FREE:
        return _PLAN_SLUG_FREE
    if t == COMMERCIAL_TIER_PRO:
        return _PLAN_SLUG_PRO
    if t == COMMERCIAL_TIER_ENTERPRISE:
        return _PLAN_SLUG_ENTERPRISE
    return frozenset()


def manifest_commercial_tiers_block() -> dict[str, Any]:
    """Serializable block for API manifest and docs alignment."""
    return {
        "ladder": [COMMERCIAL_TIER_FREE, COMMERCIAL_TIER_PRO, COMMERCIAL_TIER_ENTERPRISE],
        "plan_slug_hints": {
            "free": sorted(_PLAN_SLUG_FREE),
            "pro": sorted(_PLAN_SLUG_PRO),
            "enterprise": sorted(_PLAN_SLUG_ENTERPRISE),
        },
        "module": "apps.siteconfig.commercial_tiers",
    }
