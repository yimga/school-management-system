"""
Backward-compatible re-export: currency symbols and get_currency_symbol now live in apps.registries.currency.
Prefer: from apps.registries.currency import get_currency_symbol, CURRENCY_SYMBOLS
"""
from __future__ import annotations

from apps.registries.currency import CURRENCY_SYMBOLS, get_currency_symbol

__all__ = ["CURRENCY_SYMBOLS", "get_currency_symbol"]
