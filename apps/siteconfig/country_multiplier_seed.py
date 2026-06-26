"""Platform catalog seed for ``CountryMultiplier`` PPP bands.

Source: World Bank PPP conversion factor (GDP), indexed to US=1.0, rounded for
SaaS price bands (2024 baseline). Tax rates are indicative VAT/GST defaults;
operators may override per country in the control plane.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, TypedDict

from apps.siteconfig.global_catalog import GlobalGeoCatalog

# Provenance string stored in migration/command logs (not a DB column).
PPP_SEED_SOURCE = (
    "World Bank PPP conversion factor (GDP), US=1.0 indexed, 2024 baseline bands"
)


class CountryMultiplierSeedRow(TypedDict):
    country_code: str
    zone: str
    multiplier: Decimal
    tax_rate: Decimal
    tax_code: str
    name: str


# Curated Tier-1 / Africa / South Asia focus markets (+ US/GB/EU anchors).
COUNTRY_MULTIPLIER_SEED_ROWS: tuple[CountryMultiplierSeedRow, ...] = (
    {"country_code": "US", "zone": "A", "multiplier": Decimal("1.0000"), "tax_rate": Decimal("0.0000"), "tax_code": "", "name": "United States"},
    {"country_code": "CA", "zone": "A", "multiplier": Decimal("0.9500"), "tax_rate": Decimal("0.0500"), "tax_code": "GST/HST", "name": "Canada"},
    {"country_code": "GB", "zone": "A", "multiplier": Decimal("0.9500"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "United Kingdom"},
    {"country_code": "DE", "zone": "A", "multiplier": Decimal("0.9200"), "tax_rate": Decimal("0.1900"), "tax_code": "VAT", "name": "Germany"},
    {"country_code": "FR", "zone": "A", "multiplier": Decimal("0.9000"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "France"},
    {"country_code": "AU", "zone": "A", "multiplier": Decimal("0.9000"), "tax_rate": Decimal("0.1000"), "tax_code": "GST", "name": "Australia"},
    {"country_code": "SG", "zone": "A", "multiplier": Decimal("0.9500"), "tax_rate": Decimal("0.0900"), "tax_code": "GST", "name": "Singapore"},
    {"country_code": "AE", "zone": "B", "multiplier": Decimal("0.8500"), "tax_rate": Decimal("0.0500"), "tax_code": "VAT", "name": "United Arab Emirates"},
    {"country_code": "KE", "zone": "B", "multiplier": Decimal("0.7500"), "tax_rate": Decimal("0.1600"), "tax_code": "VAT", "name": "Kenya"},
    {"country_code": "ZA", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "South Africa"},
    {"country_code": "BR", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1700"), "tax_code": "ICMS", "name": "Brazil"},
    {"country_code": "MX", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1600"), "tax_code": "IVA", "name": "Mexico"},
    {"country_code": "MA", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Morocco"},
    {"country_code": "CM", "zone": "C", "multiplier": Decimal("0.3200"), "tax_rate": Decimal("0.1925"), "tax_code": "VAT", "name": "Cameroon"},
    {"country_code": "NG", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.0750"), "tax_code": "VAT", "name": "Nigeria"},
    {"country_code": "GH", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Ghana"},
    {"country_code": "UG", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Uganda"},
    {"country_code": "TZ", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Tanzania"},
    {"country_code": "RW", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Rwanda"},
    {"country_code": "SN", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Senegal"},
    {"country_code": "CI", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Côte d'Ivoire"},
    {"country_code": "IN", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1800"), "tax_code": "GST", "name": "India"},
    {"country_code": "PK", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1700"), "tax_code": "GST", "name": "Pakistan"},
    {"country_code": "BD", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Bangladesh"},
    {"country_code": "EG", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1400"), "tax_code": "VAT", "name": "Egypt"},
    {"country_code": "ET", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Ethiopia"},
)


def seed_country_multipliers(
    *,
    country_codes: list[str] | None = None,
    using: str = "default",
) -> dict[str, int]:
    """Upsert ``CountryMultiplier`` rows from :data:`COUNTRY_MULTIPLIER_SEED_ROWS`."""
    from django.apps import apps

    CountryMultiplier = apps.get_model("siteconfig", "CountryMultiplier")

    wanted = {
        str(row["country_code"]).strip().upper()
        for row in COUNTRY_MULTIPLIER_SEED_ROWS
    }
    if country_codes:
        normalized: set[str] = set()
        for code in country_codes:
            alpha2 = GlobalGeoCatalog.alpha2_for_country(code)
            if alpha2:
                normalized.add(alpha2.upper())
        wanted &= normalized

    created = 0
    updated = 0
    for row in COUNTRY_MULTIPLIER_SEED_ROWS:
        code = row["country_code"].upper()
        if code not in wanted:
            continue
        _, was_created = CountryMultiplier.objects.using(using).update_or_create(
            country_code=code,
            defaults={
                "zone": row["zone"],
                "multiplier": row["multiplier"],
                "tax_rate": row["tax_rate"],
                "tax_code": row["tax_code"],
                "name": row["name"],
                "is_active": True,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated, "source": PPP_SEED_SOURCE}


def all_catalog_country_codes() -> list[str]:
    """ISO alpha-2 codes from the global geo catalog (for --all expansion)."""
    codes: list[str] = []
    for item in GlobalGeoCatalog.list_countries():
        raw = str(item.get("code") or "").strip().upper()
        if not raw:
            continue
        if len(raw) == 2:
            codes.append(raw)
        elif len(raw) == 3:
            alpha2 = GlobalGeoCatalog.alpha2_for_country(raw)
            if alpha2:
                codes.append(alpha2)
    return sorted(set(codes))


def expand_seed_to_all_countries(*, using: str = "default") -> dict[str, Any]:
    """Seed curated rows, then default 1.0× Zone B for every catalog country missing a row."""
    from django.apps import apps

    CountryMultiplier = apps.get_model("siteconfig", "CountryMultiplier")

    summary = seed_country_multipliers(using=using)
    backfilled = 0
    for code in all_catalog_country_codes():
        if CountryMultiplier.objects.using(using).filter(country_code__iexact=code).exists():
            continue
        CountryMultiplier.objects.using(using).create(
            country_code=code,
            zone="B",
            multiplier=Decimal("1.0000"),
            tax_rate=Decimal("0.0000"),
            tax_code="",
            name="",
            is_active=True,
        )
        backfilled += 1
    summary["backfilled_default"] = backfilled
    return summary
