"""
Region-aware Migration Cloud vendor hints for the public signup form.

Keeps the vendor dropdown curated while surfacing what operators in each
country/region most commonly migrate from. Used by:

  - apps.siteconfig.views_country_localization (wire payload)
  - static/js/_pages/rmc-signup-country-adapter.js (reorder + hint)
  - apps.lifecycle.services_migration (locale_context on draft bundles)
"""

from __future__ import annotations

from apps.siteconfig.country_localization_service import normalize_country_code

# Stable slugs aligned with templates/schools/signup_school.html + signup_views.
_ALL_VENDORS: tuple[str, ...] = (
    "powerschool",
    "blackbaud",
    "veracross",
    "infinite_campus",
    "alma",
    "facts",
    "skyward",
    "managebac",
    "toddle",
    "oneroster",
    "csv",
    "other",
)

_NORTH_AMERICA = frozenset({"US", "CA", "MX"})
_UK_IE = frozenset({"GB", "IE"})
_ANZ = frozenset({"AU", "NZ"})
_EAST_ASIA = frozenset(
    {"CN", "TW", "HK", "MO", "JP", "KR", "SG", "MY", "VN", "TH", "ID", "PH"}
)
_AFRICA_ANGLO = frozenset(
    {"NG", "GH", "KE", "UG", "TZ", "ZA", "ZM", "ZW", "BW", "NA", "RW", "SL", "LR"}
)
_AFRICA_FRANCO = frozenset(
    {"CM", "SN", "CI", "BF", "ML", "NE", "TG", "BJ", "GA", "CG", "CD", "MG", "MA", "TN", "DZ"}
)
_EU_IB = frozenset({"CH", "BE", "NL", "DE", "AT", "FR", "ES", "IT", "PT"})


def recommended_migration_vendors(country_code: str | None) -> list[str]:
    """Return vendor slugs ordered for the given country (most likely first)."""
    cc = normalize_country_code(country_code)
    if not cc:
        return list(_ALL_VENDORS)

    if cc in _NORTH_AMERICA:
        priority = (
            "powerschool",
            "infinite_campus",
            "skyward",
            "blackbaud",
            "veracross",
            "alma",
            "facts",
            "managebac",
            "toddle",
            "oneroster",
            "csv",
            "other",
        )
    elif cc in _UK_IE or cc in _ANZ:
        priority = (
            "managebac",
            "blackbaud",
            "veracross",
            "toddle",
            "alma",
            "powerschool",
            "csv",
            "oneroster",
            "other",
        )
    elif cc in _EAST_ASIA:
        priority = (
            "csv",
            "managebac",
            "toddle",
            "blackbaud",
            "veracross",
            "oneroster",
            "powerschool",
            "other",
        )
    elif cc in _AFRICA_ANGLO:
        priority = (
            "csv",
            "powerschool",
            "blackbaud",
            "managebac",
            "veracross",
            "alma",
            "oneroster",
            "other",
        )
    elif cc in _AFRICA_FRANCO:
        priority = (
            "csv",
            "blackbaud",
            "managebac",
            "veracross",
            "powerschool",
            "oneroster",
            "other",
        )
    elif cc in _EU_IB:
        priority = (
            "managebac",
            "toddle",
            "blackbaud",
            "veracross",
            "alma",
            "csv",
            "oneroster",
            "other",
        )
    else:
        priority = _ALL_VENDORS

    seen: set[str] = set()
    ordered: list[str] = []
    for slug in priority:
        if slug in seen:
            continue
        seen.add(slug)
        ordered.append(slug)
    for slug in _ALL_VENDORS:
        if slug not in seen:
            ordered.append(slug)
    return ordered


def migration_hint_for_country(country_code: str | None) -> str:
    """One-line helper copy under the migration vendor picker."""
    cc = normalize_country_code(country_code)
    if cc in _EAST_ASIA:
        return (
            "Spreadsheet exports and international-school platforms are common here. "
            "We pre-map columns to your local calendar and education cycles."
        )
    if cc in _AFRICA_ANGLO or cc in _AFRICA_FRANCO:
        return (
            "CSV / spreadsheet imports work offline-first. Pick your prior SIS if listed — "
            "we draft a locale-aware Migration Cloud bundle on day one."
        )
    if cc in _NORTH_AMERICA:
        return (
            "District SIS exports (PowerSchool, Infinite Campus, Skyward) map cleanly. "
            "Your calendar and cycle picks above flow into the bundle."
        )
    if cc in _UK_IE or cc in _ANZ or cc in _EU_IB:
        return (
            "Independent and IB schools often migrate from ManageBac, Blackbaud, or Veracross. "
            "We preserve your term structure from the selections above."
        )
    return (
        "We'll draft a Migration Cloud bundle aligned with your country, calendar, "
        "and education cycles. CSV works fully offline."
    )


def migration_context_for_country(country_code: str | None) -> dict:
    """JSON-safe blob for signup adapter + migration_intent handoff."""
    cc = normalize_country_code(country_code)
    return {
        "country_code": cc,
        "recommended_vendors": recommended_migration_vendors(cc),
        "hint": migration_hint_for_country(cc),
    }


# Onboarding wizard uses ``spreadsheet`` where signup uses ``csv``.
_ONBOARDING_VENDOR_ALIASES: dict[str, str] = {"csv": "spreadsheet"}


def recommended_onboarding_vendor_slugs(country_code: str | None) -> list[str]:
    """Signup recommendation order mapped to onboarding vendor slugs."""
    ordered: list[str] = []
    seen: set[str] = set()
    for slug in recommended_migration_vendors(country_code):
        mapped = _ONBOARDING_VENDOR_ALIASES.get(slug, slug)
        if mapped in seen:
            continue
        seen.add(mapped)
        ordered.append(mapped)
    return ordered


def order_onboarding_vendors(vendors, country_code: str | None):
    """Return onboarding vendor tiles ordered for the session country."""
    rank = {
        slug: idx for idx, slug in enumerate(recommended_onboarding_vendor_slugs(country_code))
    }
    return sorted(vendors, key=lambda vendor: rank.get(vendor.slug, 999))
