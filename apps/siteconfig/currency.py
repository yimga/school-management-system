"""
Backward-compatible re-export: currency symbols and get_currency_symbol now live in apps.registries.currency.
Prefer: from apps.registries.currency import get_currency_symbol, CURRENCY_SYMBOLS
"""

from __future__ import annotations

from apps.registries.currency import (
    CURRENCY_SYMBOLS,
    format_money,
    get_currency_decimal_places,
    get_currency_symbol,
)

__all__ = [
    "CURRENCY_SYMBOLS",
    "format_money",
    "get_currency_decimal_places",
    "get_currency_symbol",
    "platform_currency_symbol",
]


def platform_currency_symbol() -> str:
    from django.conf import settings

    code = (getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD") or "USD").upper()
    return get_currency_symbol(code)
