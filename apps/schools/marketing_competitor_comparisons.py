"""Honest 'RunMyCampus vs <competitor>' comparison data (SEO landing pages).

HONESTY CONTRACT — read before editing
=======================================
1. Every RunMyCampus cell must reflect a capability that is SHIPPED per
   apps/schools/feature_gap_register.py (offline-first PWA, mobile-money rails,
   multi-tenant isolation, OneRoster org tree, EMIS aggregate pipeline, country
   governance matrix, AI center, etc.). Do NOT claim anything not shipped.
2. Competitor cells describe PUBLIC market positioning only — neutral, factual,
   non-disparaging. No invented weaknesses, no fabricated numbers. Each page
   carries a visible disclaimer that competitor info is based on public
   marketing as of 2026 and may change; readers should verify with the vendor.
3. The angle is "where RunMyCampus is differentiated for emerging-market /
   multi-campus / offline-first contexts" — benefit-led, not mud-slinging.
"""

from __future__ import annotations

from typing import Optional, TypedDict

_DISCLAIMER = (
    "Comparison based on each vendor's public marketing and documentation as of "
    "2026 and on RunMyCampus shipped capabilities. Vendor capabilities change — "
    "please verify current details with each provider. Not affiliated with or "
    "endorsed by the named vendors."
)


class CompareRow(TypedDict):
    capability: str
    runmycampus: str
    competitor: str
    note: str


class Comparison(TypedDict):
    slug: str
    competitor_name: str
    seo_title: str
    seo_description: str
    hero_headline: str
    intro: str
    disclaimer: str
    rows: list[CompareRow]
    cta_label: str
    cta_route: str


# Shared RunMyCampus differentiators (all map to shipped feature-gap rows).
def _rows(competitor_positions: dict[str, str]) -> list[CompareRow]:
    base = {
        "Offline-first operation": (
            "Offline-first PWA — attendance, records and queued actions keep "
            "working through connectivity drops, syncing on reconnect."
        ),
        "Mobile-money fee collection": (
            "Built-in mobile-money rails (Paystack, Flutterwave, MTN MoMo, Orange "
            "Money) alongside card — region-aware."
        ),
        "Multi-tenant / multi-campus isolation": (
            "Tenant-first architecture with per-campus isolation and group-level "
            "oversight from one control plane."
        ),
        "Interoperability": (
            "OneRoster org-tree sync + open API and webhooks."
        ),
        "Government reporting": (
            "EMIS aggregate pipeline + a country governance matrix for local "
            "compliance patterns."
        ),
        "Localization": (
            "Multi-language UI incl. RTL, region-aware currency and messaging "
            "channels (WhatsApp / SMS where available)."
        ),
        "Deployment model": (
            "Cloud or self-host; same kernel from 2G offline PWA to large NOC."
        ),
    }
    rows: list[CompareRow] = []
    for cap, ours in base.items():
        rows.append(
            {
                "capability": cap,
                "runmycampus": ours,
                "competitor": competitor_positions.get(cap, "—"),
                "note": "",
            }
        )
    return rows


_COMPARISONS: dict[str, Comparison] = {
    "powerschool": {
        "slug": "powerschool",
        "competitor_name": "PowerSchool",
        "seo_title": "RunMyCampus vs PowerSchool — offline-first, mobile-money, multi-campus",
        "seo_description": (
            "How RunMyCampus compares to PowerSchool for offline-first operation, "
            "mobile-money fee collection, and multi-campus deployments. Honest, "
            "public-positioning comparison."
        ),
        "hero_headline": "RunMyCampus vs PowerSchool",
        "intro": (
            "PowerSchool is a large, established North-American SIS ecosystem. "
            "RunMyCampus is built for schools and networks that need offline-first "
            "resilience, mobile-money collection and fast multi-campus rollout — "
            "often in emerging and connectivity-variable markets."
        ),
        "disclaimer": _DISCLAIMER,
        "rows": _rows(
            {
                "Offline-first operation": "Cloud SIS; rich online ecosystem.",
                "Mobile-money fee collection": "Payments oriented to North-American rails.",
                "Multi-tenant / multi-campus isolation": "District-scale deployments.",
                "Interoperability": "Broad integration marketplace and APIs.",
                "Government reporting": "Strong US state-reporting coverage.",
                "Localization": "Primarily North-American market focus.",
                "Deployment model": "Cloud-hosted SaaS.",
            }
        ),
        "cta_label": "See a tailored walkthrough",
        "cta_route": "marketing_demo",
    },
    "blackbaud": {
        "slug": "blackbaud",
        "competitor_name": "Blackbaud",
        "seo_title": "RunMyCampus vs Blackbaud — modern operations for schools & networks",
        "seo_description": (
            "RunMyCampus vs Blackbaud: offline-first operations, mobile-money "
            "rails, and tenant-first multi-campus architecture. Honest comparison."
        ),
        "hero_headline": "RunMyCampus vs Blackbaud",
        "intro": (
            "Blackbaud serves private and independent schools with a long-standing "
            "enrollment, fundraising and tuition suite. RunMyCampus focuses on "
            "day-to-day operations that stay resilient offline and collect fees on "
            "the rails families actually use."
        ),
        "disclaimer": _DISCLAIMER,
        "rows": _rows(
            {
                "Offline-first operation": "Cloud-hosted suite.",
                "Mobile-money fee collection": "Tuition management oriented to card/ACH.",
                "Multi-tenant / multi-campus isolation": "Independent-school focus.",
                "Interoperability": "Established integrations across its suite.",
                "Government reporting": "Independent-school oriented.",
                "Localization": "Primarily US/UK independent schools.",
                "Deployment model": "Cloud-hosted SaaS.",
            }
        ),
        "cta_label": "Talk to us",
        "cta_route": "marketing_demo",
    },
    "arbor": {
        "slug": "arbor",
        "competitor_name": "Arbor",
        "seo_title": "RunMyCampus vs Arbor — beyond the UK MIS, for global networks",
        "seo_description": (
            "RunMyCampus vs Arbor: offline-first, mobile-money, multi-region "
            "governance and multi-campus isolation for global school networks."
        ),
        "hero_headline": "RunMyCampus vs Arbor",
        "intro": (
            "Arbor is a popular cloud MIS for UK schools and trusts. RunMyCampus "
            "targets globally distributed networks that need offline resilience, "
            "local payment rails and multi-country governance out of the box."
        ),
        "disclaimer": _DISCLAIMER,
        "rows": _rows(
            {
                "Offline-first operation": "Cloud MIS.",
                "Mobile-money fee collection": "UK payment + parental engagement focus.",
                "Multi-tenant / multi-campus isolation": "MAT (multi-academy trust) support.",
                "Interoperability": "UK MIS integrations and APIs.",
                "Government reporting": "Strong UK statutory reporting.",
                "Localization": "Primarily UK market.",
                "Deployment model": "Cloud-hosted SaaS.",
            }
        ),
        "cta_label": "Plan a rollout",
        "cta_route": "marketing_demo",
    },
}


def _normalize(slug: str) -> str:
    return slug.strip().lower() if slug else ""


def comparison_for_slug(slug: str) -> Optional[Comparison]:
    """Return the comparison for ``slug`` (case-insensitive), or ``None``."""
    return _COMPARISONS.get(_normalize(slug))


def all_comparison_slugs() -> list[str]:
    return list(_COMPARISONS.keys())
