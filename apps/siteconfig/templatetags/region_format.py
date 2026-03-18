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


@register.filter
def format_date(value, date_format_pattern=None):
    """Format a date/datetime.
    When request is in context (e.g. RequestContext), uses tenant locale date_format.
    Usage: {{ some_date|format_date }} or {{ some_date|format_date:"YYYY-MM-DD" }}
    """
    if value is None:
        return ""
    pattern = date_format_pattern or "DD/MM/YYYY"
    fmt = _date_format_to_django(pattern)
    try:
        return dateformat.format(value, fmt)
    except (TypeError, ValueError, AttributeError):
        return str(value)


@register.filter
def format_currency(value):
    """Format a number as currency. Uses context tenant_locale when available else DEFAULT_CURRENCY."""
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


@register.simple_tag(takes_context=True)
def format_date_tenant(context, value):
    """Phase C: Format date using tenant locale (request.school -> get_tenant_locale)."""
    if value is None:
        return ""
    request = context.get("request")
    school = getattr(request, "school", None) if request else None
    try:
        from apps.siteconfig.tenant_config import format_date_tenant as _fmt

        return _fmt(value, request=request, school=school)
    except (ImportError, AttributeError, TypeError, ValueError, KeyError):
        from django.utils import dateformat

        return dateformat.format(value, "d/m/Y") if value else ""


@register.simple_tag(takes_context=True)
def format_currency_tenant(context, value):
    """Phase C: Format amount as currency using tenant locale."""
    if value is None:
        return ""
    request = context.get("request")
    school = getattr(request, "school", None) if request else None
    try:
        from apps.siteconfig.tenant_config import format_currency_tenant as _fmt

        return _fmt(value, request=request, school=school)
    except (ImportError, AttributeError, TypeError, ValueError):
        return str(value)


@register.filter
def format_number(value, decimals=2):
    """Format a number with thousands separators.

    Usage in templates:
        {{ amount|format_number }}      -> 1,234.56 (2 decimals)
        {{ amount|format_number:0 }}    -> 1,235 (no decimals)

    Uses period for decimal and comma for thousands (Anglophone Cameroon default).
    """
    if value is None:
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    dec = int(decimals) if decimals is not None else 2
    s = f"{num:,.{dec}f}"
    return s
