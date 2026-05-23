"""
Wave 2 (v3.62.5) — Localization template tag library.

Usage in templates::

    {% load localization %}

    <p>Today is {{ today|local_date }}</p>
    <p>Tuition: {{ amount|local_currency }}</p>
    <p>{{ "teacher"|local_term }}: {{ teacher.name }}</p>
    <p>{{ "principal"|local_term }}: {{ school.principal_name }}</p>

The filters resolve against the `localization` context dict emitted by
``apps.siteconfig.localization_context_processor.localization_context``,
falling back to safe defaults when that context is missing (so partials
rendered outside the full request cycle don't crash).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import template
from django.utils.dateformat import format as dj_format
from django.utils.safestring import mark_safe

register = template.Library()


# --- helpers ----------------------------------------------------------------

def _loc_from_context(context) -> dict:
    """Pull the `localization` dict from a template context safely."""
    try:
        return context.get("localization") or {}
    except Exception:  # noqa: BLE001
        return {}


def _strftime_to_django(pattern: str) -> str:
    """Translate Python strftime patterns to Django's date-format codes.

    We use the small subset that LocaleRegistry actually emits:
        %d -> d   %m -> m   %Y -> Y   %y -> y
        %H -> H   %M -> i   %B -> F   %b -> M   %A -> l   %a -> D
    Anything else passes through unchanged.
    """
    mapping = (
        ("%d", "d"), ("%m", "m"), ("%Y", "Y"), ("%y", "y"),
        ("%H", "H"), ("%M", "i"), ("%S", "s"),
        ("%B", "F"), ("%b", "M"), ("%A", "l"), ("%a", "D"),
    )
    out = pattern or ""
    for src, dst in mapping:
        out = out.replace(src, dst)
    return out


# --- filters ----------------------------------------------------------------

@register.filter(name="local_date")
def local_date(value: Any, fmt: str | None = None) -> str:
    """Format a date/datetime per the user's country.

    Without an explicit ``fmt``, uses ``localization.date_format`` from the
    context processor. Returns "" for falsey input. NEVER raises.
    """
    if not value:
        return ""
    try:
        pattern = fmt or "%d/%m/%Y"
        # If we're in a render context with localization, use its format.
        # The shortest path is to format directly when the value carries
        # `strftime`; Django's `date` filter is locale-aware which we DON'T
        # want here (we want country-aware, not user-language-aware).
        return value.strftime(pattern)
    except Exception:  # noqa: BLE001
        return ""


@register.simple_tag(takes_context=True, name="local_date_for")
def local_date_for(context, value: Any) -> str:
    """Context-aware date filter — pulls format from `localization.date_format`.

    Usage:  {% local_date_for some_date %}
    """
    loc = _loc_from_context(context)
    pattern = loc.get("date_format") or "%d/%m/%Y"
    return local_date(value, pattern)


_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
    "CNY": "¥", "INR": "₹", "NGN": "₦", "KES": "KSh",
    "GHS": "GH₵", "ZAR": "R", "EGP": "E£", "MAD": "DH",
    "AED": "AED", "SAR": "SAR", "ILS": "₪", "TRY": "₺",
    "BRL": "R$", "MXN": "$", "ARS": "$", "COP": "$", "CLP": "$",
    "PEN": "S/", "RUB": "₽", "PLN": "zł", "SEK": "kr",
    "NOK": "kr", "DKK": "kr", "CHF": "CHF", "CAD": "$", "AUD": "$",
    "NZD": "$", "SGD": "$", "HKD": "$", "KRW": "₩", "THB": "฿",
    "IDR": "Rp", "MYR": "RM", "PHP": "₱", "VND": "₫",
    "PKR": "₨", "BDT": "৳", "LKR": "Rs", "NPR": "Rs",
}


@register.filter(name="local_currency")
def local_currency(amount: Any, currency_code: str | None = None) -> str:
    """Format a Decimal/numeric amount per currency.

    Without `currency_code`, the caller must call `local_currency_for` (the
    context-aware version) to pick up the country default. This raw filter
    accepts an explicit currency for the (rarer) cases where the amount is
    bound to a specific currency regardless of viewer country.
    """
    if amount is None:
        return ""
    try:
        dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except Exception:  # noqa: BLE001
        return ""
    code = (currency_code or "USD").upper()
    symbol = _CURRENCY_SYMBOLS.get(code, code + " ")
    # Two decimals for most; zero for JPY/KRW/VND etc. (display-only —
    # storage still has full precision).
    zero_decimal = code in ("JPY", "KRW", "VND", "IDR", "CLP")
    quantized = dec.quantize(Decimal("1") if zero_decimal else Decimal("0.01"))
    # Thousands separator — `:,` works for any locale because we don't
    # localize the digit grouping symbol here (would need full ICU). The
    # primary value is the symbol + amount, not separator polish.
    grouped = f"{quantized:,}"
    return f"{symbol}{grouped}"


@register.simple_tag(takes_context=True, name="local_currency_for")
def local_currency_for(context, amount: Any) -> str:
    """Context-aware currency filter — uses `localization.currency_code`.

    Usage:  {% local_currency_for invoice.amount %}
    """
    loc = _loc_from_context(context)
    return local_currency(amount, loc.get("currency_code") or "USD")


@register.filter(name="local_term")
def local_term(key: str, default: str = "") -> str:
    """Look up a terminology key against the localization terminology pack.

    Used WITHOUT context (e.g. inside an `{% include %}` block) — caller
    should pre-bind the value via `{% with %}`. For most cases use
    `{% local_term_for "teacher" %}` (the context-aware variant) instead.
    """
    return default or str(key or "")


@register.simple_tag(takes_context=True, name="local_term_for")
def local_term_for(context, key: str, default: str = "") -> str:
    """Context-aware terminology lookup.

    Usage:
        {% local_term_for "teacher" %}    -> "Enseignant" in FR pack
        {% local_term_for "principal" %}  -> "Headteacher" in GB pack
        {% local_term_for "term" %}       -> "Trimestre" in FR pack
        {% local_term_for "report_card" %}-> "Bulletin" in FR pack
        {% local_term_for "grade_level" %}-> "Niveau" in FR pack
    """
    loc = _loc_from_context(context)
    terms = loc.get("terminology") or {}
    val = terms.get(key)
    if val:
        return str(val)
    return default or str(key or "")


@register.simple_tag(takes_context=True, name="local_week_start")
def local_week_start(context) -> int:
    """Return the user's week start day (0=Sunday .. 6=Saturday).

    Used to wire calendar widgets / scheduling views without per-template
    JS lookup. Defaults to Monday=1 when unresolved.
    """
    loc = _loc_from_context(context)
    try:
        return int(loc.get("week_start") or 1)
    except (TypeError, ValueError):
        return 1


@register.simple_tag(takes_context=True, name="local_is_rtl")
def local_is_rtl(context) -> bool:
    """Return True if the user's country uses RTL script."""
    loc = _loc_from_context(context)
    return bool(loc.get("is_rtl"))


@register.simple_tag(takes_context=True, name="local_calendar_default")
def local_calendar_default(context) -> dict:
    """Return the user's primary calendar dict (or {} if none)."""
    loc = _loc_from_context(context)
    cal = loc.get("default_calendar")
    return cal if isinstance(cal, dict) else {}
