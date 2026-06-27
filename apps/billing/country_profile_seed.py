"""Reusable seed for ``CountryBillingProfile`` — the per-country commercial policy
(currency, market tier, billing cycles, payment methods, tax behavior, procurement
and promotion knobs) that makes the platform's pricing configurable for every
country rather than a hardcoded handful.

Shared by ``manage.py seed_country_billing_profiles`` (operator/CLI) and the data
migration that activates the full 250-country footprint on deploy. Models are
resolved via ``apps.get_model`` and choice values are raw strings (mirroring the
model's TextChoices) so the function is safe to call from a migration's historical
app state — the same pattern as ``siteconfig.country_multiplier_seed``.

Every value here is a DEFAULT an operator can override per country in the control
plane; nothing is locked. Unconfigured countries still degrade safely (base USD,
neutral multiplier) via ``tenant_pricing.country_billing_profile_for``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import DatabaseError

from apps.registries.country_currency_map import currency_for_country


# Choice VALUES mirror CountryBillingProfile.{PublicPriceMode,TaxBehavior} and
# CountryMultiplier.Zone — kept as literals so this runs against historical models.
_PRICE_MODE_PUBLISHED = "PUBLISHED"
_PRICE_MODE_LOCALIZED = "LOCALIZED"
_TAX_EXCLUSIVE = "EXCLUSIVE"
_TAX_MANUAL = "MANUAL"

TIER_A_PAYMENT_METHODS = ["card", "bank_transfer", "invoice", "purchase_order"]
TIER_B_PAYMENT_METHODS = ["card", "bank_transfer", "mobile_money", "invoice", "purchase_order"]
TIER_C_PAYMENT_METHODS = [
    "card", "bank_transfer", "mobile_money", "invoice", "purchase_order", "sponsorship",
]

TIER_A_CYCLES = ["monthly", "annual", "school_year", "custom_contract"]
TIER_B_CYCLES = ["monthly", "annual", "school_year", "custom_contract"]
TIER_C_CYCLES = ["monthly", "annual", "school_year", "sponsored", "custom_contract"]


@dataclass(frozen=True)
class CountrySeed:
    code: str
    name: str
    currency: str
    language: str


EXTRA_MARKET_ROWS = (
    CountrySeed(code="XK", name="Kosovo", currency="EUR", language="sq"),
    CountrySeed(code="ZZ", name="Global fallback market", currency="USD", language="en"),
)


def _catalog_country_rows(get_model) -> list[CountrySeed]:
    """Every catalog country: prefer the CountryRegistry SOT, fall back to pycountry."""
    rows: list[CountrySeed] = []
    try:
        CountryRegistry = get_model("registries", "CountryRegistry")
        for country in CountryRegistry.objects.filter(is_active=True).order_by("code"):
            code = str(country.code or "").upper()[:2]
            rows.append(
                CountrySeed(
                    code=code,
                    name=country.name,
                    # canonical CLDR map wins so the long tail isn't stuck on USD
                    currency=(currency_for_country(code) or country.default_currency or "USD").upper()[:3],
                    language=country.default_language or "en",
                )
            )
    except (LookupError, DatabaseError, AttributeError, RuntimeError, ValueError):
        rows = []

    if not rows:
        try:
            from apps.siteconfig.global_catalog import GlobalGeoCatalog

            for item in GlobalGeoCatalog.list_countries():
                code = str(
                    item.get("code_alpha2") or item.get("code") or ""
                ).upper()[:2]
                if not code:
                    continue
                defaults = GlobalGeoCatalog.country_defaults(code)
                rows.append(
                    CountrySeed(
                        code=code,
                        name=item.get("name") or defaults.get("name") or code,
                        currency=(currency_for_country(code) or defaults.get("currency") or "USD").upper()[:3],
                        language=defaults.get("default_language") or "en",
                    )
                )
        except (ImportError, DatabaseError, AttributeError, RuntimeError, ValueError):
            rows = []

    rows.extend(EXTRA_MARKET_ROWS)
    deduped = {row.code: row for row in rows if row.code}
    return [deduped[key] for key in sorted(deduped)]


def _market_tier(multiplier) -> str:
    zone = (getattr(multiplier, "zone", "") or "B").upper()
    return zone if zone in {"A", "B", "C"} else "B"


def _payment_methods_for(tier: str) -> list[str]:
    if tier == "A":
        return list(TIER_A_PAYMENT_METHODS)
    if tier == "C":
        return list(TIER_C_PAYMENT_METHODS)
    return list(TIER_B_PAYMENT_METHODS)


def _cycles_for(tier: str) -> list[str]:
    if tier == "A":
        return list(TIER_A_CYCLES)
    if tier == "C":
        return list(TIER_C_CYCLES)
    return list(TIER_B_CYCLES)


def _price_mode_for(tier: str) -> str:
    return _PRICE_MODE_PUBLISHED if tier == "A" else _PRICE_MODE_LOCALIZED


def _profile_defaults(row: CountrySeed, multiplier) -> dict[str, Any]:
    tier = _market_tier(multiplier)
    tax_code = getattr(multiplier, "tax_code", "") or ""
    # multi-year discount: richer markets get a smaller incentive than emerging ones
    multi_year_discount = 15 if tier in {"A", "B"} else 20  # magic-number-allow: default discount %
    annual_discount = 10  # magic-number-allow: default annual discount %
    return {
        "country_name": row.name,
        "currency_code": row.currency,
        "market_tier": tier,
        "price_zone": tier,
        "public_price_mode": _price_mode_for(tier),
        "default_billing_cycles": _cycles_for(tier),
        "payment_methods": _payment_methods_for(tier),
        "tax_behavior": _TAX_EXCLUSIVE if tax_code else _TAX_MANUAL,
        "invoice_locale": row.language,
        "checkout_copy": {
            "headline": "Your local billing options",
            "summary": "Plan, billing cycle, payment method, and add-ons can be adjusted for this country.",
        },
        "procurement_policy": {
            "purchase_orders": True,
            "offline_invoice": True,
            "mobile_money_review": tier in {"B", "C"},
            "government_contracts": True,
            "ngo_sponsorship_review": tier == "C",
        },
        "promotion_policy": {
            "annual_discount_percent": annual_discount,
            "multi_year_discount_percent": multi_year_discount,
            "sponsorship_allowed": tier == "C",
        },
        "addon_policy": {
            "usage_bundles": True,
            "country_overrides": True,
            "operator_approval_for_sensitive_addons": True,
        },
        "metadata": {
            "seed_source": "registry_or_global_catalog",
            "configurable": True,
            "country_multiplier_present": multiplier is not None,
        },
        "is_active": True,
    }


def seed_country_billing_profiles(*, using: str = "default") -> dict[str, int]:
    """Upsert a CountryBillingProfile for every catalog country. Idempotent."""
    from django.apps import apps

    CountryBillingProfile = apps.get_model("billing", "CountryBillingProfile")
    CountryMultiplier = apps.get_model("siteconfig", "CountryMultiplier")

    multipliers = {
        m.country_code.upper(): m
        for m in CountryMultiplier.objects.using(using).filter(is_active=True)
    }
    created = updated = fallback = 0
    for row in _catalog_country_rows(apps.get_model):
        multiplier = multipliers.get(row.code.upper())
        if multiplier is None:
            fallback += 1
        _, was_created = CountryBillingProfile.objects.using(using).update_or_create(
            country_code=row.code,
            defaults=_profile_defaults(row, multiplier),
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {
        "profiles": created + updated,
        "created": created,
        "updated": updated,
        "fallback_countries": fallback,
    }
