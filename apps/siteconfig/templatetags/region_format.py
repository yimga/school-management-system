"""
Template filters for region-aware formatting (date, currency, number).

Requires the region_settings context processor in production so templates receive
date_format, currency_symbol, decimal_separator, thousands_separator. When rendering
without RequestContext (e.g. PDF generation), pass the same keys in the context so
these filters work correctly.

Note: format_currency takes a single value argument and uses context when available
(via resolve_currency_context) so that Django's template engine only requires one
template-provided argument.
"""
from decimal import Decimal

from django import template
from django.conf import settings
from django.utils import dateformat

register = template.Library()


def _resolve_currency_context(context):
    """Get currency symbol and separators from context or settings defaults."""
    if context:
        symbol = context.get("currency_symbol")
        dec_sep = context.get("decimal_separator")
        thousands_sep = context.get("thousands_separator")
        if symbol is not None and dec_sep is not None and thousands_sep is not None:
            return symbol or "", dec_sep or ".", thousands_sep or ","
    from apps.siteconfig.currency import get_currency_symbol
    currency = getattr(settings, "DEFAULT_CURRENCY", "XAF")
    symbol = get_currency_symbol(currency)
    return symbol, ".", ","


def _date_format_to_django(pattern: str) -> str:
    """Convert placeholder pattern (DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD) to Django date format (d, m, Y)."""
    if not pattern:
        return "d/m/Y"
    s = pattern.replace("YYYY", "Y").replace("DD", "d").replace("MM", "m")
    return s


@register.filter(takes_context=True)
def format_date(context, value=None):
    """Format a date/datetime using the region's date_format from context.
    Value defaults to None so Django counts one template-provided argument (required 1, provided 1).
    """
    if value is None:
        return ""
    pattern = context.get("date_format") or "DD/MM/YYYY"
    fmt = _date_format_to_django(pattern)
    try:
        return dateformat.format(value, fmt)
    except Exception:
        return str(value)


@register.filter
def format_currency(value):
    """Format a number as currency. Uses DEFAULT_CURRENCY and default separators (no context)."""
    if value is None:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    symbol, dec_sep, thousands_sep = _resolve_currency_context(None)
    s = f"{amount:,.2f}"
    s = s.replace(".", "\x00").replace(",", thousands_sep).replace("\x00", dec_sep)
    return f"{symbol}{s}" if symbol else s


@register.filter(takes_context=True)
def format_number(context, value, decimals=2):
    """Format a number using region's decimal_separator and thousands_separator from context."""
    if value is None:
        return ""
    try:
        if isinstance(value, Decimal):
            num = float(value)
        else:
            num = float(value)
    except (TypeError, ValueError):
        return str(value)
    dec_sep = context.get("decimal_separator") or "."
    thousands_sep = context.get("thousands_separator") or ","
    dec = int(decimals) if decimals is not None else 2
    s = f"{num:,.{dec}f}"
    s = s.replace(".", "\x00").replace(",", thousands_sep).replace("\x00", dec_sep)
    return s
