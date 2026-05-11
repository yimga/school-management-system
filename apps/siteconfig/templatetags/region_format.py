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

    currency = (
        getattr(settings, "PLATFORM_DEFAULT_CURRENCY", None)
        or getattr(settings, "DEFAULT_CURRENCY", None)
        or "USD"
    )
    symbol = get_currency_symbol(currency)
    return symbol, ".", ","


def _date_format_to_django(pattern: str) -> str:
    """Convert placeholder pattern (DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD) to Django date format (d, m, Y).

    Falls back to ISO 8601 (Y-m-d) when no pattern is supplied — ISO is the only locale-neutral
    format that's unambiguous worldwide. Do NOT assume DD/MM/YYYY: that's a UK/EU convention
    and would render incorrectly for US, Japan, China, and other tenants.
    """
    if not pattern:
        return "Y-m-d"
    if not isinstance(pattern, str):
        return "Y-m-d"
    s = pattern.replace("YYYY", "Y").replace("DD", "d").replace("MM", "m")
    return s


def _format_date_value(value, pattern: str) -> str:
    if value is None:
        return ""
    fmt = _date_format_to_django(pattern)
    try:
        return dateformat.format(value, fmt)
    except (TypeError, ValueError, AttributeError):
        return str(value)


@register.filter
def format_date(value, date_format_pattern=None):
    """Format a date/datetime.

    Template usage: ``{{ some_date|format_date }}`` or ``{{ some_date|format_date:"YYYY-MM-DD" }}``.

    Unit tests and PDF-style renderers may call ``format_date(locale_ctx, dt)`` where *locale_ctx*
    is a dict with ``date_format`` (same keys as the region_settings context processor).

    Defaults to ISO 8601 (YYYY-MM-DD) when no pattern is supplied; this is the only
    locale-neutral default that does not silently mis-render dates for tenants in the US,
    Japan, China, or other non-DD/MM/YYYY conventions.
    """
    if isinstance(value, dict):
        ctx = value
        inner = date_format_pattern
        if inner is None:
            return ""
        pattern = ctx.get("date_format") or "YYYY-MM-DD"
        return _format_date_value(inner, pattern)
    return _format_date_value(value, date_format_pattern or "YYYY-MM-DD")


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

        # ISO 8601 fallback when tenant locale resolution fails — unambiguous worldwide.
        return dateformat.format(value, "Y-m-d") if value else ""


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


def _format_number_value(
    num: float, decimals: int, dec_sep: str, thousands_sep: str
) -> str:
    s = f"{num:,.{decimals}f}"
    s = s.replace(".", "\x00").replace(",", thousands_sep).replace("\x00", dec_sep)
    return s


def _format_number_from_ctx(ctx: dict, inner, dec_override: int = 2) -> str:
    dec_sep = ctx.get("decimal_separator")
    thousands_sep = ctx.get("thousands_separator")
    if dec_sep is None:
        dec_sep = "."
    if thousands_sep is None:
        thousands_sep = ","
    try:
        num = float(inner)
    except (TypeError, ValueError):
        return str(inner)
    dec = int(dec_override) if dec_override is not None else 2
    return _format_number_value(num, dec, str(dec_sep), str(thousands_sep))


def _format_number_plain(value, decimals=2) -> str:
    if value is None:
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals is None:
        dec = 2
    else:
        dec = int(decimals)
    return _format_number_value(num, dec, ".", ",")


@register.filter
def format_number(first, second=None, third=None):
    """Format a number; optional locale dict for separators (tests / PDF helpers).

    Templates: ``{{ amount|format_number }}`` or ``{{ amount|format_number:0 }}``.

    Python: ``format_number(ctx, value)`` or ``format_number(ctx, value, 0)`` with
    ``decimal_separator`` / ``thousands_separator`` on *ctx* (same as region_settings).
    """
    if isinstance(first, dict):
        inner = second
        if inner is None:
            return ""
        dec_arg = 2 if third is None else third
        return _format_number_from_ctx(first, inner, dec_arg)
    return _format_number_plain(first, second)
