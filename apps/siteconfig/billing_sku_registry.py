"""
BR-10 plan SKU bundles (machine-readable).

Human narrative: ``docs/BILLING_SKUS_ENTITLEMENTS.md``. This module is the canonical
registry for tier → default ``Plan.included_features``-style codes used in API manifest
and seeding helpers — not a second strategy doc.

Feature codes are lowercase slugs aligned with ``School.features`` / marketplace modules
(see ``apps/schools/tests/test_plan_and_feature_gate.py`` and tenant compiler).
"""

from __future__ import annotations

from typing import Final

# BR-10 tier slugs (stable for manifest and operator UIs)
BR10_TIER_CORE: Final[str] = "core"
BR10_TIER_INTEROP: Final[str] = "interop"
BR10_TIER_INTELLIGENCE: Final[str] = "intelligence"

# Default feature slugs per tier (superset of common modules; tenants may add more ad hoc).
BR10_TIER_FEATURE_BUNDLES: Final[dict[str, frozenset[str]]] = {
    BR10_TIER_CORE: frozenset(
        {
            "library",
            "transport",
            "reports",
            "finance",
            "messaging",
            "documents",
            "syllabus",
        }
    ),
    BR10_TIER_INTEROP: frozenset(
        {
            "oneroster",
            "lti",
            "scim",
            "district_hub",
        }
    ),
    BR10_TIER_INTELLIGENCE: frozenset(
        {
            "analytics",
            "ai_gateway",
            "ews",
        }
    ),
}

ALL_BR10_CANONICAL_FEATURE_CODES: Final[frozenset[str]] = frozenset().union(
    *BR10_TIER_FEATURE_BUNDLES.values()
)

# --- Report platform SKUs (Batch 14+; bounded-context depth, no DDL this slice) ---
# Named bundles for plan/add-on wiring and manifest discovery. The coarse module gate
# used across the product remains the single code ``reports`` on ``Plan.included_features``;
# granular codes below are optional: enable in plans or ``School.addons`` when a surface
# checks ``is_feature_enabled`` / policy; ministry, parent PDF, custom-builder, scheduled,
# staff publish/promotion-preview, and related API paths use
# ``FEATURE_GATE_PATH_ANY_OF`` in ``apps/schools/middleware.py`` (see BILLING_SKUS_ENTITLEMENTS.md).
REPORT_PLATFORM_SKU_STANDARD: Final[str] = "reports-standard"
REPORT_PLATFORM_SKU_ADVANCED: Final[str] = "reports-advanced"

REPORT_PLATFORM_SKU_BUNDLES: Final[dict[str, frozenset[str]]] = {
    REPORT_PLATFORM_SKU_STANDARD: frozenset(
        {
            "reports",
            "reports_pdf_exports",
            "reports_template_library",
        }
    ),
    REPORT_PLATFORM_SKU_ADVANCED: frozenset(
        {
            "reports",
            "reports_pdf_exports",
            "reports_template_library",
            "reports_custom_builder",
            "reports_scheduled_delivery",
            "reports_ministry_exports",
        }
    ),
}

ALL_REPORT_PLATFORM_FEATURE_CODES: Final[frozenset[str]] = frozenset().union(
    *REPORT_PLATFORM_SKU_BUNDLES.values()
)


def normalize_plan_feature_codes(raw: object) -> list[str]:
    """Dedupe, lowercase, strip; preserves order of first occurrence."""
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for x in raw:
        s = str(x).strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def suggested_features_for_br10_tier(tier_slug: str) -> frozenset[str]:
    """Return the canonical bundle for a tier, or empty if unknown."""
    key = str(tier_slug or "").strip().lower()
    return BR10_TIER_FEATURE_BUNDLES.get(key, frozenset())


def ordered_features_for_br10_tier(tier_slug: str) -> list[str]:
    """Sorted feature list for ``Plan.included_features`` JSON (deterministic seeds)."""
    return sorted(suggested_features_for_br10_tier(tier_slug))


def ordered_features_for_report_platform_bundle(bundle_slug: str) -> list[str]:
    """
    Sorted feature codes for a report-platform SKU bundle (``REPORT_PLATFORM_SKU_*``).

    Use with ``Plan.included_features`` when seeding optional report-tier plans aligned
    with ``manifest_report_platform_skus_block`` / HTTP feature gates.
    """
    key = str(bundle_slug or "").strip().lower()
    codes = REPORT_PLATFORM_SKU_BUNDLES.get(key)
    if not codes:
        return []
    return sorted(codes)


def manifest_report_platform_skus_block() -> dict[str, object]:
    """Report-platform SKU bundles for manifest and operator alignment (additive to BR-10 tiers)."""
    return {
        "bundles": {
            slug: sorted(codes) for slug, codes in REPORT_PLATFORM_SKU_BUNDLES.items()
        },
        "all_feature_codes": sorted(ALL_REPORT_PLATFORM_FEATURE_CODES),
    }


def get_operator_default_report_platform_bundle_slug() -> str | None:
    """
    Validated bundle slug from ``PlatformReportPlatformSkuDefault`` (pk=1), or None.

    Used for manifest surfacing and tenant read-models without re-querying feature sets.
    """
    try:
        from django.db import DatabaseError, OperationalError

        from apps.platform_runtime.models import PlatformReportPlatformSkuDefault

        row = PlatformReportPlatformSkuDefault.objects.filter(pk=1).first()
    except (ImportError, DatabaseError, OperationalError, RuntimeError):
        return None
    if not row or not row.default_bundle_slug:
        return None
    s = str(row.default_bundle_slug).strip().lower()
    return s if s in REPORT_PLATFORM_SKU_BUNDLES else None


def get_operator_report_platform_bundle_feature_codes() -> frozenset[str]:
    """
    Feature codes granted by the platform singleton ``PlatformReportPlatformSkuDefault`` (pk=1).

    Empty when unset, unknown slug, or DB unavailable. Used as a **floor** for granular
    report-platform codes only when the tenant already has coarse ``reports`` on
    plan/addons/School.features (see ``is_plan_entitlement_feature_enabled``).
    """
    slug = get_operator_default_report_platform_bundle_slug()
    if not slug:
        return frozenset()
    return REPORT_PLATFORM_SKU_BUNDLES[slug]


def manifest_plan_entitlements_block() -> dict[str, object]:
    """Stable JSON-serializable block for ``/api/v1/manifest.json``."""
    from apps.siteconfig.commercial_tiers import manifest_commercial_tiers_block

    out: dict[str, object] = {
        "br10_reference": "docs/BILLING_SKUS_ENTITLEMENTS.md",
        "registry_module": "apps.siteconfig.billing_sku_registry",
        "tiers": {
            tier: sorted(codes) for tier, codes in BR10_TIER_FEATURE_BUNDLES.items()
        },
        "all_canonical_codes": sorted(ALL_BR10_CANONICAL_FEATURE_CODES),
        "report_platform_skus": manifest_report_platform_skus_block(),
        "commercial_packaging": manifest_commercial_tiers_block(),
    }
    slug = get_operator_default_report_platform_bundle_slug()
    if slug:
        out["operator_default_report_platform_bundle"] = slug
    return out


def get_effective_report_platform_floor_codes_for_school(school) -> frozenset[str]:
    """
    Feature codes for the plan-entitlement **floor** when the tenant has coarse ``reports``.

    Per-school ``report_platform_bundle_slug`` (if a known bundle) **replaces** the platform
    operator default for that tenant; empty slug falls back to
    ``get_operator_report_platform_bundle_feature_codes()``.
    """
    if school is not None:
        raw = getattr(school, "report_platform_bundle_slug", None) or ""
        s = str(raw).strip().lower()
        if s and s in REPORT_PLATFORM_SKU_BUNDLES:
            return REPORT_PLATFORM_SKU_BUNDLES[s]
    return get_operator_report_platform_bundle_feature_codes()


def get_effective_report_platform_bundle_slug_for_school(
    school, *, operator_default_slug: str | None = None
) -> str | None:
    """
    Bundle slug used for the report-platform entitlement **floor** on this school.

    School override wins when it is a known bundle slug; otherwise the operator default
    applies. Pass ``operator_default_slug`` from a single query when listing many schools
    to avoid N+1 DB reads.
    """
    if school is not None:
        raw = getattr(school, "report_platform_bundle_slug", None) or ""
        s = str(raw).strip().lower()
        if s and s in REPORT_PLATFORM_SKU_BUNDLES:
            return s
    if operator_default_slug is not None:
        return (
            operator_default_slug
            if operator_default_slug in REPORT_PLATFORM_SKU_BUNDLES
            else None
        )
    return get_operator_default_report_platform_bundle_slug()
