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

from contextvars import ContextVar

from django import template
from django.conf import settings
from django.utils import dateformat

register = template.Library()

# Memoise the resolved (symbol, dec_sep, thousands_sep) per pinned school_id so a
# statement rendering many amounts does not re-query the School for each value.
# Keyed by school_id and only used when the *live* pin still matches, so it never
# bleeds one tenant's currency into another's request.
_PINNED_CURRENCY: ContextVar = ContextVar("rmc_pinned_currency", default=None)


def _resolve_pinned_tenant_currency():
    """``(symbol, dec_sep, thousands_sep)`` for the request's pinned tenant, or None.

    The ``format_currency`` filter cannot receive the template context (Django
    filters never do), so without this it always rendered the platform-default
    symbol — a school billing in XAF/NGN/KES saw "$" on its own invoices. We
    resolve the currency from the per-request tenant pin (set and reset by
    ``TenantBoundaryCoreGuardMiddleware``) so tenant-facing money documents render
    the school's own currency, while operator / control-plane pages (no pin) keep
    the platform default. Returns None when no tenant is pinned.
    """
    try:
        from apps.tenancy.boundary_core_guard import get_pinned_school_id

        school_id = get_pinned_school_id()
    except (ImportError, AttributeError):
        return None
    if not school_id:
        return None
    cached = _PINNED_CURRENCY.get()
    if cached is not None and cached[0] == school_id:
        return cached[1]
    try:
        from django.db import Error as _DBError
        from apps.schools.models import School
        from apps.siteconfig.currency import get_currency_symbol

        school = (
            School.objects.filter(pk=school_id).select_related("default_region").first()
        )
        if school is None:
            return None
        code = (school.resolve_currency() or "").strip().upper()
        if not code:
            return None
        # Number separators are locale-specific (e.g. francophone "12 500,50").
        # Resolve them from the school's region exactly as the region_settings
        # context processor does, defaulting to en-style when the region is unset.
        region = getattr(school, "default_region", None)
        dec_sep = (getattr(region, "decimal_separator", None) or ".") if region else "."
        thousands_sep = (
            (getattr(region, "thousands_separator", None) or ",") if region else ","
        )
        resolved = (get_currency_symbol(code), dec_sep, thousands_sep, code)
    except (ImportError, AttributeError, TypeError, ValueError, _DBError):
        return None
    _PINNED_CURRENCY.set((school_id, resolved))
    return resolved


def _resolve_currency_context(context):
    """Get ``(symbol, dec_sep, thousands_sep, currency_code)`` from context, the
    request's pinned tenant, or settings defaults — in that order.

    ``currency_code`` is what lets the caller pick the currency's real minor-unit
    digit count + symbol placement; it may be ``None`` on the legacy context path
    when only a display symbol is known.
    """
    if context:
        symbol = context.get("currency_symbol")
        dec_sep = context.get("decimal_separator")
        thousands_sep = context.get("thousands_separator")
        if symbol is not None and dec_sep is not None and thousands_sep is not None:
            return (
                symbol or "",
                dec_sep or ".",
                thousands_sep or ",",
                context.get("currency_code"),
            )
    pinned = _resolve_pinned_tenant_currency()
    if pinned is not None:
        return pinned
    from apps.siteconfig.currency import get_currency_symbol

    currency = (
        getattr(settings, "PLATFORM_DEFAULT_CURRENCY", None)
        or getattr(settings, "DEFAULT_CURRENCY", None)
        or "USD"
    )
    symbol = get_currency_symbol(currency)
    return symbol, ".", ",", currency


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
    """Format a number as currency using the request-pinned tenant's currency.

    Routes through ``apps.registries.currency.format_money`` so the amount honours
    the currency's real minor-unit digit count and symbol placement — e.g. a
    Cameroon (XAF) fee renders ``50 000 FCFA``, not ``FCFA50,000.00``.
    """
    if value is None:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    symbol, dec_sep, thousands_sep, code = _resolve_currency_context(None)
    from apps.registries.currency import format_money

    return format_money(
        amount, code, symbol=symbol, decimal_sep=dec_sep, thousands_sep=thousands_sep
    )


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
def format_dual_date_tenant(context, value):
    """Format date with optional Hijri/Buddhist/Hebrew annotation for tenant school."""
    if value is None:
        return ""
    request = context.get("request")
    school = getattr(request, "school", None) if request else None
    try:
        from apps.platform_runtime.calendar_display import format_dual_calendar_date

        return format_dual_calendar_date(value, school=school)
    except (ImportError, AttributeError, TypeError, ValueError):
        return format_date_tenant(context, value)


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
    dec = 2 if decimals is None else int(decimals)
    # The scalar filter can't see template context, so resolve the pinned tenant's
    # separators the same way ``format_currency`` does — a francophone school then
    # renders "12 500,50" instead of the hardcoded "12,500.50". Falls back to the
    # en-style ./, when there is no tenant pin / no region separators configured.
    resolved = _resolve_pinned_tenant_currency()
    if resolved:
        _symbol, dec_sep, thousands_sep, _code = resolved
    else:
        dec_sep, thousands_sep = ".", ","
    return _format_number_value(num, dec, dec_sep or ".", thousands_sep or ",")


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
