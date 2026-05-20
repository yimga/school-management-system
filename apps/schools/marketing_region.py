"""Local-first · global-next marketing region helpers (public site)."""

from __future__ import annotations

from typing import Any

# ISO 3166-1 alpha-2 profiles with canonical /<lang>/<cc>/ routes (+ legacy shortcuts).
MARKETING_REGION_PROFILES: dict[str, dict[str, str]] = {
    "CM": {
        "default_language": "fr",
        "legacy_path": "/cm/",
        "region_label": "Cameroon",
    },
    "CA": {
        "default_language": "en",
        "legacy_path": "/ca/",
        "region_label": "Canada",
    },
    "NG": {
        "default_language": "en",
        "legacy_path": "",
        "region_label": "Nigeria",
    },
    "GB": {
        "default_language": "en",
        "legacy_path": "",
        "region_label": "United Kingdom",
    },
    "GH": {
        "default_language": "en",
        "legacy_path": "",
        "region_label": "Ghana",
    },
    "KE": {
        "default_language": "en",
        "legacy_path": "",
        "region_label": "Kenya",
    },
    "ZA": {
        "default_language": "en",
        "legacy_path": "",
        "region_label": "South Africa",
    },
    "US": {
        "default_language": "en",
        "legacy_path": "",
        "region_label": "United States",
    },
}

# Country codes surfaced in the header picker (order = display).
MARKETING_REGION_PICKER_CODES: tuple[str, ...] = (
    "CM",
    "CA",
    "NG",
    "GB",
    "GH",
    "KE",
    "ZA",
    "US",
)

# Extra regulatory cards beyond the base FERPA/COPPA/GDPR grid.
_EXTRA_REGULATORY_BY_COUNTRY: dict[str, tuple[dict[str, str], ...]] = {
    "ZA": (
        {
            "id": "popia",
            "title": "POPIA",
            "summary": "South African personal-information law—processor posture and school-as-controller workflows.",
            "url_name": "marketing_trust_gdpr",
            "deep_dive_label": "Privacy & POPIA pack",
            "highlight": "1",
        },
    ),
    "NG": (
        {
            "id": "ndpr",
            "title": "Nigeria NDPR",
            "summary": "Data-protection expectations for schools processing personal data in Nigeria.",
            "url_name": "marketing_trust_gdpr",
            "deep_dive_label": "Privacy pack",
            "highlight": "1",
        },
    ),
    "GB": (
        {
            "id": "uk_gdpr",
            "title": "UK GDPR",
            "summary": "UK data-protection alignment for schools and academy trusts.",
            "url_name": "marketing_trust_gdpr",
            "deep_dive_label": "UK GDPR pack",
            "highlight": "1",
        },
    ),
    "US": (
        {
            "id": "ny_ed_law",
            "title": "NY Ed Law § 2-d",
            "summary": "New York student-data privacy expectations for vendors—contract and security addenda.",
            "url_name": "marketing_trust_ferpa",
            "deep_dive_label": "FERPA & state privacy",
            "highlight": "1",
        },
    ),
    "CA": (
        {
            "id": "pipeda",
            "title": "PIPEDA / provincial",
            "summary": "Canadian privacy expectations vary by province—we document processor posture in the security packet.",
            "url_name": "marketing_trust_gdpr",
            "deep_dive_label": "Privacy pack",
            "highlight": "1",
        },
    ),
}

# Highlight base card ids per country (ferpa, gdpr, coppa, accessibility, retention, incidents).
_REGULATORY_HIGHLIGHT_IDS: dict[str, frozenset[str]] = {
    "US": frozenset({"ferpa", "coppa"}),
    "GB": frozenset({"gdpr", "accessibility"}),
    "ZA": frozenset({"gdpr", "popia"}),
    "NG": frozenset({"gdpr"}),
    "CM": frozenset({"gdpr"}),
    "CA": frozenset({"gdpr"}),
    "GH": frozenset({"gdpr"}),
    "KE": frozenset({"gdpr"}),
}


def normalize_marketing_country(value: str) -> str:
    raw = (value or "").strip().upper()[:2]
    return raw if raw in MARKETING_REGION_PROFILES else ""


def regional_landing_path(country_code: str, language_code: str | None = None) -> str:
    code = normalize_marketing_country(country_code)
    if not code:
        return "/"
    profile = MARKETING_REGION_PROFILES[code]
    lang = (language_code or profile["default_language"] or "en").strip().lower()
    lang = lang.split("-", 1)[0] or "en"
    return f"/{lang}/{code.lower()}/"


def regional_picker_options() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for code in MARKETING_REGION_PICKER_CODES:
        profile = MARKETING_REGION_PROFILES[code]
        rows.append(
            {
                "country_code": code,
                "label": profile["region_label"],
                "path": regional_landing_path(code),
                "default_language": profile["default_language"],
            }
        )
    return rows


def build_marketing_region_affordance(
    *,
    country_code: str,
    country_label: str,
    language_code: str,
    is_regional_page: bool = False,
) -> dict[str, Any]:
    """Header chip + regional landing link for local-first positioning."""
    code = normalize_marketing_country(country_code)
    profile = MARKETING_REGION_PROFILES.get(code) if code else None
    detected_label = (country_label or "").strip() or (
        profile["region_label"] if profile else ""
    )
    landing_path = regional_landing_path(code, language_code) if code else ""
    return {
        "marketing_region_detected_code": code,
        "marketing_region_detected_label": detected_label or "Global",
        "marketing_region_landing_path": landing_path,
        "marketing_region_is_regional_page": bool(is_regional_page),
        "marketing_region_picker_options": regional_picker_options(),
        "marketing_region_show_affordance": bool(code and landing_path),
    }


def trust_regulatory_cards_for_country(
    base_cards: list[dict[str, str]],
    country_code: str,
) -> list[dict[str, Any]]:
    """Order regulatory grid with country-relevant frameworks first."""
    code = normalize_marketing_country(country_code)
    highlight_ids = _REGULATORY_HIGHLIGHT_IDS.get(code, frozenset())
    extras = list(_EXTRA_REGULATORY_BY_COUNTRY.get(code, ()))

    enriched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in base_cards:
        cid = str(card.get("id") or "")
        row = dict(card)
        row["highlight"] = cid in highlight_ids
        enriched.append(row)
        seen.add(cid)

    for extra in extras:
        eid = str(extra.get("id") or "")
        if eid and eid not in seen:
            row = dict(extra)
            row["highlight"] = str(extra.get("highlight", "")) == "1"
            enriched.append(row)
            seen.add(eid)

    enriched.sort(
        key=lambda c: (0 if c.get("highlight") else 1, str(c.get("title") or ""))
    )
    return enriched


def institution_regional_callout(
    institution_slug: str,
    *,
    country_code: str,
    country_label: str,
) -> dict[str, str] | None:
    """Optional regional lead line for solution segment pages."""
    code = normalize_marketing_country(country_code)
    label = (country_label or "").strip()
    slug = (institution_slug or "").strip().lower()
    if not code or not label or label == "Global":
        return None

    if slug == "international-schools":
        if code in {"CM", "NG", "GH", "KE", "ZA"}:
            return {
                "eyebrow": f"{label} · International schools",
                "body": (
                    f"Multi-currency finance, mobile families, and governance your "
                    f"{label} board can explain—without a separate product per country."
                ),
            }
        return {
            "eyebrow": f"{label} · International schools",
            "body": (
                f"Calendars, grading pathways, and family portals tuned for {label} "
                "campuses on one worldwide operating core."
            ),
        }

    if slug == "multi-campus":
        return {
            "eyebrow": f"{label} · School groups",
            "body": (
                f"Standardize policy and reporting across {label} campuses without "
                "erasing local calendars, currencies, or compliance defaults."
            ),
        }

    if slug in {"k12", "k12-schools", "private-schools"}:
        return {
            "eyebrow": f"{label} · K–12",
            "body": (
                f"Daily operations—attendance through report cards—on {label} "
                "term structures and fee models, not a generic template."
            ),
        }

    return {
        "eyebrow": f"{label}",
        "body": (
            f"Local-first configuration for {label}; global-ready when you add "
            "campuses or cross-border groups."
        ),
    }
