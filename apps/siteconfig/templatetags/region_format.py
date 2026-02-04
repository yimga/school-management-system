"""
Template filters for region-aware formatting (date, currency, number).

Requires the region_settings context processor in production so templates receive
date_format, currency_symbol, decimal_separator, thousands_separator. When rendering
without RequestContext (e.g. PDF generation), pass the same keys in the context so
these filters work correctly.
"""
from decimal import Decimal

from django import template
from django.utils import dateformat

register = template.Library()


def _date_format_to_django(pattern: str) -> str:
    """Convert placeholder pattern (DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD) to Django date format (d, m, Y)."""
    if not pattern:
        return "d/m/Y"
    s = pattern.replace("YYYY", "Y").replace("DD", "d").replace("MM", "m")
    return s


@register.filter(takes_context=True)
def format_date(context, value):
    """Format a date/datetime using the region's date_format from context."""
    if value is None:
        return ""
    pattern = context.get("date_format") or "DD/MM/YYYY"
    fmt = _date_format_to_django(pattern)
    try:
        return dateformat.format(value, fmt)
    except Exception:
        return str(value)


@register.filter(takes_context=True)
def format_currency(context, value):
    """Format a number as currency using region's currency_symbol and separators from context."""
    if value is None:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    symbol = context.get("currency_symbol") or ""
    dec_sep = context.get("decimal_separator") or "."
    thousands_sep = context.get("thousands_separator") or ","
    s = f"{amount:,.2f}"
    # Replace decimal point first (temp), then thousands, then temp with dec_sep
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
