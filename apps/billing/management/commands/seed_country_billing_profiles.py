from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db import DatabaseError, transaction

from apps.billing.models import CountryBillingProfile
from apps.siteconfig.models_platform_catalog import CountryMultiplier


@dataclass(frozen=True)
class CountrySeed:
    code: str
    name: str
    currency: str
    language: str


TIER_A_PAYMENT_METHODS = ["card", "bank_transfer", "invoice", "purchase_order"]
TIER_B_PAYMENT_METHODS = [
    "card",
    "bank_transfer",
    "mobile_money",
    "invoice",
    "purchase_order",
]
TIER_C_PAYMENT_METHODS = [
    "card",
    "bank_transfer",
    "mobile_money",
    "invoice",
    "purchase_order",
    "sponsorship",
]

TIER_A_CYCLES = ["monthly", "annual", "school_year", "custom_contract"]
TIER_B_CYCLES = ["monthly", "annual", "school_year", "custom_contract"]
TIER_C_CYCLES = ["monthly", "annual", "school_year", "sponsored", "custom_contract"]

EXTRA_MARKET_ROWS = (
    CountrySeed(code="XK", name="Kosovo", currency="EUR", language="sq"),
    CountrySeed(code="ZZ", name="Global fallback market", currency="USD", language="en"),
)


def _catalog_country_rows() -> list[CountrySeed]:
    rows: list[CountrySeed] = []
    try:
        from apps.registries.models import CountryRegistry

        for country in CountryRegistry.objects.filter(is_active=True).order_by("code"):
            rows.append(
                CountrySeed(
                    code=str(country.code or "").upper()[:2],
                    name=country.name,
                    currency=(country.default_currency or "USD").upper()[:3],
                    language=country.default_language or "en",
                )
            )
    except (ImportError, DatabaseError, AttributeError, RuntimeError, ValueError):
        rows = []
    if rows:
        rows.extend(EXTRA_MARKET_ROWS)
        deduped = {row.code: row for row in rows if row.code}
        return [deduped[key] for key in sorted(deduped)]

    try:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        for item in GlobalGeoCatalog.list_countries():
            code = str(
                item.get("code_alpha2")
                or item.get("country_code_alpha2")
                or item.get("code")
                or ""
            ).upper()[:2]
            if not code:
                continue
            defaults = GlobalGeoCatalog.country_defaults(code)
            rows.append(
                CountrySeed(
                    code=code,
                    name=item.get("name") or defaults.get("name") or code,
                    currency=(defaults.get("currency") or "USD").upper()[:3],
                    language=defaults.get("default_language") or "en",
                )
            )
    except (ImportError, DatabaseError, AttributeError, RuntimeError, ValueError):
        rows = []
    rows.extend(EXTRA_MARKET_ROWS)
    deduped = {row.code: row for row in rows if row.code}
    return [deduped[key] for key in sorted(deduped)]


def _multiplier_for(code: str) -> CountryMultiplier | None:
    return CountryMultiplier.objects.filter(country_code__iexact=code, is_active=True).first()


def _market_tier(multiplier: CountryMultiplier | None) -> str:
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
    if tier == "A":
        return CountryBillingProfile.PublicPriceMode.PUBLISHED
    if tier == "C":
        return CountryBillingProfile.PublicPriceMode.LOCALIZED
    return CountryBillingProfile.PublicPriceMode.LOCALIZED


class Command(BaseCommand):
    help = "Seed configurable per-country billing profiles for global pricing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        rows = _catalog_country_rows()
        summary = {"profiles": 0, "fallback_countries": 0}

        for row in rows:
            multiplier = _multiplier_for(row.code)
            tier = _market_tier(multiplier)
            tax_code = getattr(multiplier, "tax_code", "") or ""
            defaults = {
                "country_name": row.name,
                "currency_code": row.currency,
                "market_tier": tier,
                "price_zone": tier,
                "public_price_mode": _price_mode_for(tier),
                "default_billing_cycles": _cycles_for(tier),
                "payment_methods": _payment_methods_for(tier),
                "tax_behavior": (
                    CountryBillingProfile.TaxBehavior.EXCLUSIVE
                    if tax_code
                    else CountryBillingProfile.TaxBehavior.MANUAL
                ),
                "invoice_locale": row.language,
                "checkout_copy": {
                    "headline": "Your local billing options",
                    "summary": "Plan, billing cycle, payment method, and add-ons can be adjusted for this country.",
                },
                "procurement_policy": {
                    "purchase_orders": tier in {"A", "B", "C"},
                    "offline_invoice": True,
                    "mobile_money_review": tier in {"B", "C"},
                    "government_contracts": True,
                    "ngo_sponsorship_review": tier == "C",
                },
                "promotion_policy": {
                    "annual_discount_percent": 10,
                    "multi_year_discount_percent": 15 if tier in {"A", "B"} else 20,
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
            if multiplier is None:
                summary["fallback_countries"] += 1
            if dry_run:
                self.stdout.write(f"[dry-run] country {row.code}: {defaults}")
            else:
                CountryBillingProfile.objects.update_or_create(
                    country_code=row.code,
                    defaults=defaults,
                )
            summary["profiles"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Country billing profile seed complete "
                f"(profiles={summary['profiles']}, "
                f"fallback_countries={summary['fallback_countries']})."
            )
        )
