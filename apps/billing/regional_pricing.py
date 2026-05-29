"""v4.00.36 — pure regional-pricing helper.

Combines the existing PPP ``CountryMultiplier`` row with the new
``tax_rate`` field to compute a locally-adjusted price. Pure: no DB
mutation, no I/O outside a single SELECT on ``CountryMultiplier``.

Contract::

    LocalizedPrice(subtotal, tax, total, currency_code, multiplier, tax_rate)

``subtotal = base_usd * multiplier``; ``tax = subtotal * tax_rate``;
``total = subtotal + tax``. When the country is not registered, the
helper returns the base price unchanged (multiplier=1, tax_rate=0,
currency=USD) so missing data never silently zeroes out a tenant's bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


_TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class LocalizedPrice:
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    currency_code: str
    multiplier: Decimal
    tax_rate: Decimal
    tax_code: str
    country_code: str


def _q(value: Decimal) -> Decimal:
    return value.quantize(_TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_country_row(country_code: str) -> Any | None:
    if not country_code:
        return None
    try:
        from apps.siteconfig.models_platform_catalog import CountryMultiplier
    except (ImportError, RuntimeError):
        return None
    try:
        # tenant-isolation-allow: country-multiplier-is-platform-catalog-not-tenant-scoped
        return CountryMultiplier.objects.filter(
            country_code__iexact=country_code,
            is_active=True,
        ).first()
    except (AttributeError, RuntimeError, ValueError):
        return None


def _resolve_currency_for_country(country_code: str) -> str:
    if not country_code:
        return "USD"
    try:
        from apps.registries.models import CountryRegistry
    except (ImportError, RuntimeError):
        return "USD"
    try:
        row = CountryRegistry.objects.filter(code__iexact=country_code).only(
            "default_currency"
        ).first()
    except (AttributeError, RuntimeError, ValueError):
        return "USD"
    return (getattr(row, "default_currency", None) or "USD") if row else "USD"


def compute_localized_price(
    base_usd: Decimal | float | int | str,
    country_code: str,
    *,
    currency_override: str | None = None,
    subdivision_code: str | None = None,
) -> LocalizedPrice:
    """Return a localized-price record for a base USD amount and country.

    Missing country rows fall back to multiplier=1, tax_rate=0, USD —
    we never silently zero-out a bill due to a missing registry entry.

    v4.00.36 Phase 3: tax_rate now flows through the pluggable
    ``apps.billing.tax_engine.resolve_tax_rate`` so a live tax engine
    (Avalara / TaxJar / Stripe Tax) can override the static value when
    a tenant configures one.
    """
    base = Decimal(str(base_usd or 0))
    row = _resolve_country_row(country_code)
    multiplier = Decimal(str(getattr(row, "multiplier", 1) or 1)) if row else Decimal("1")
    tax_code = (getattr(row, "tax_code", "") or "") if row else ""
    subtotal = _q(base * multiplier)
    tax_rate = _resolve_tax_rate(country_code, subdivision_code, row)
    tax = _q(subtotal * tax_rate)
    total = _q(subtotal + tax)
    currency = (currency_override or _resolve_currency_for_country(country_code) or "USD").upper()
    return LocalizedPrice(
        subtotal=subtotal,
        tax=tax,
        total=total,
        currency_code=currency,
        multiplier=multiplier,
        tax_rate=tax_rate,
        tax_code=tax_code,
        country_code=(country_code or "").upper(),
    )


def _resolve_tax_rate(
    country_code: str, subdivision_code: str | None, fallback_row: Any | None
) -> Decimal:
    try:
        from apps.billing.tax_engine import resolve_tax_rate

        return resolve_tax_rate(country_code, subdivision_code=subdivision_code)
    except (ImportError, RuntimeError, AttributeError, ValueError, TypeError):
        if fallback_row is None:
            return Decimal("0")
        try:
            return Decimal(str(getattr(fallback_row, "tax_rate", 0) or 0))
        except (TypeError, ValueError):
            return Decimal("0")


__all__ = ["LocalizedPrice", "compute_localized_price"]
