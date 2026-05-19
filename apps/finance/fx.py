"""
Decimal-safe FX helpers (settings.EXCHANGE_RATES table or env JSON).

Rates are expressed as units of currency per 1 USD unless keyed as FROM_TO pairs.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.conf import settings


def _rates_table() -> dict[str, Any]:
    raw = getattr(settings, "EXCHANGE_RATES", None) or {}
    return raw if isinstance(raw, dict) else {}


def exchange_rate_decimal(from_currency: str, to_currency: str) -> Decimal | None:
    """Return multiply factor: amount_in_from * rate = amount_in_to."""
    src = (from_currency or "").strip().upper()
    dst = (to_currency or "").strip().upper()
    if not src or not dst:
        return None
    if src == dst:
        return Decimal("1")

    rates = _rates_table()
    pair = rates.get(f"{src}_{dst}")
    if pair is not None:
        try:
            return Decimal(str(pair))
        except (TypeError, ValueError, ArithmeticError):
            return None

    def _per_usd(code: str) -> Decimal | None:
        if not code:
            return None
        for key in (code, f"USD_{code}"):
            val = rates.get(key)
            if val is not None:
                try:
                    return Decimal(str(val))
                except (TypeError, ValueError, ArithmeticError):
                    return None
        return None

    from_usd = _per_usd(src)
    to_usd = _per_usd(dst)
    if from_usd and to_usd and from_usd > 0:
        return (to_usd / from_usd).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return None


def convert_amount_decimal(
    amount: Decimal | str | float | int,
    from_currency: str,
    to_currency: str,
) -> Decimal:
    """Convert with Decimal precision; raises ValueError when rate missing."""
    amt = Decimal(str(amount))
    rate = exchange_rate_decimal(from_currency, to_currency)
    if rate is None:
        raise ValueError(
            f"No exchange rate configured for {from_currency!r} -> {to_currency!r}"
        )
    return (amt * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def exchange_rate_api_payload(from_currency: str, to_currency: str) -> dict[str, str]:
    rate = exchange_rate_decimal(from_currency, to_currency)
    if rate is None:
        raise ValueError("rate unavailable")
    return {
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "rate": format(rate, "f"),
        "source": "settings.EXCHANGE_RATES",
    }
