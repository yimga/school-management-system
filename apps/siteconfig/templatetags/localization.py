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


# Wave 7 (v3.62.8 2026-05-22): countries that use Indian (lakh-crore)
# digit grouping for ALL numbers (currency + counts + invoices). Indian
# numbering writes 1,00,000 (lakh) not 100,000, then 1,00,00,000 (crore)
# not 10,000,000.
_INDIAN_GROUPING_COUNTRIES = frozenset({"IN", "PK", "BD", "NP", "LK", "BT", "MV"})

# Wave 10 (v3.62.10 — 2026-05-22): countries that opt into CJK myriad
# (萬 / 億) grouping for fee statements and academic reports.
_MYRIAD_GROUPING_COUNTRIES = frozenset({"CN", "JP", "KR", "TW", "HK"})


def _group_indian(digits: str) -> str:
    """Group an integer digit string with Indian lakh-crore convention.

    "1234567"   -> "12,34,567"
    "12345678"  -> "1,23,45,678"
    "100"       -> "100"
    """
    if len(digits) <= 3:
        return digits
    last3 = digits[-3:]
    rest = digits[:-3]
    # Walk from the right inserting commas every 2 digits.
    out_chunks = []
    i = len(rest)
    while i > 2:
        out_chunks.insert(0, rest[i-2:i])
        i -= 2
    if i > 0:
        out_chunks.insert(0, rest[:i])
    return ",".join(out_chunks) + "," + last3


def _group_western(digits: str) -> str:
    """Standard 1,234,567 grouping (every 3 digits)."""
    if len(digits) <= 3:
        return digits
    out_chunks = []
    i = len(digits)
    while i > 3:
        out_chunks.insert(0, digits[i-3:i])
        i -= 3
    if i > 0:
        out_chunks.insert(0, digits[:i])
    return ",".join(out_chunks)


def _group_myriad(digits: str, use_native_marks: bool = False) -> str:
    """CJK myriad (萬/億) grouping: every 4 digits.

    "100000000" -> "1,0000,0000" or "1億0000萬0000" with native marks.
    """
    if len(digits) <= 4:
        return digits
    chunks = []
    i = len(digits)
    while i > 4:
        chunks.insert(0, digits[i-4:i])
        i -= 4
    if i > 0:
        chunks.insert(0, digits[:i])
    if use_native_marks:
        marks = ["", "萬", "億", "兆"]
        out = ""
        for k, chunk in enumerate(chunks):
            pos = len(chunks) - 1 - k
            out += chunk + (marks[pos] if 0 < pos < len(marks) else "")
        return out
    return ",".join(chunks)


def _group_for_country(country_code: str | None, digits: str, *, native_marks: bool = False) -> str:
    cc = (country_code or "").upper()
    if cc in _INDIAN_GROUPING_COUNTRIES:
        return _group_indian(digits)
    if cc in _MYRIAD_GROUPING_COUNTRIES:
        return _group_myriad(digits, use_native_marks=native_marks)
    return _group_western(digits)


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
    # Default Western grouping; the context-aware sibling can pass Indian.
    grouped = f"{quantized:,}"
    return f"{symbol}{grouped}"


@register.filter(name="local_number")
def local_number(value: Any, country_code: str | None = None) -> str:
    """Format an integer/decimal with country-aware digit grouping (Wave 7).

    Indian countries get lakh-crore (1,23,456); the rest get Western
    (1,234,567). Pass ``country_code`` explicitly or use
    ``{% local_number_for value %}`` (context-aware) to pick up the user's
    country from the localization context processor.
    """
    if value is None or value == "":
        return ""
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:  # noqa: BLE001
        return ""
    # Preserve fractional component when present.
    sign = "-" if dec < 0 else ""
    dec = abs(dec)
    s = format(dec, "f")
    if "." in s:
        int_part, frac_part = s.split(".", 1)
        frac_part = frac_part.rstrip("0")
    else:
        int_part, frac_part = s, ""
    grouped = _group_for_country(country_code, int_part)
    return sign + grouped + (("." + frac_part) if frac_part else "")


@register.simple_tag(takes_context=True, name="local_number_for")
def local_number_for(context, value: Any) -> str:
    """Context-aware Wave 7 number-grouping helper.

    Usage:  {% local_number_for student_count %}
    """
    loc = _loc_from_context(context)
    return local_number(value, loc.get("country_code") or "")


@register.simple_tag(takes_context=True, name="local_currency_grouped_for")
def local_currency_grouped_for(context, amount: Any) -> str:
    """Currency formatter that ALSO honors Indian digit grouping.

    Sister of ``local_currency_for`` for the rare path where you specifically
    want lakh-crore grouping (e.g. fee statements in India). Most call
    sites should keep using ``local_currency_for`` (Western grouping) for
    operator-readable consistency with prior reports.
    """
    if amount is None:
        return ""
    loc = _loc_from_context(context)
    try:
        dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except Exception:  # noqa: BLE001
        return ""
    code = (loc.get("currency_code") or "USD").upper()
    symbol = _CURRENCY_SYMBOLS.get(code, code + " ")
    zero_decimal = code in ("JPY", "KRW", "VND", "IDR", "CLP")
    quantized = dec.quantize(Decimal("1") if zero_decimal else Decimal("0.01"))
    sign = "-" if quantized < 0 else ""
    quantized = abs(quantized)
    s = format(quantized, "f")
    if "." in s:
        int_part, frac_part = s.split(".", 1)
    else:
        int_part, frac_part = s, ""
    grouped = _group_for_country(loc.get("country_code") or "", int_part)
    if frac_part:
        return f"{symbol}{sign}{grouped}.{frac_part}"
    return f"{symbol}{sign}{grouped}"


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


# --- Wave 4 format helpers --------------------------------------------------

@register.simple_tag(takes_context=True, name="local_full_name")
def local_full_name(context, given: str, family: str) -> str:
    """Render a person's full name in the country's order.

    Usage:  {% local_full_name student.given_name student.family_name %}
        - US → "Naomi Tanaka"
        - JP → "Tanaka Naomi"
        - HU → "Tanaka Naomi"
    """
    try:
        from apps.siteconfig.country_formats_service import compose_full_name
    except ImportError:
        # Fallback: simple given + family
        return f"{(given or '').strip()} {(family or '').strip()}".strip()
    loc = _loc_from_context(context)
    return compose_full_name(given or "", family or "", loc.get("country_code") or "")


@register.simple_tag(takes_context=True, name="local_dial_code")
def local_dial_code(context) -> str:
    """Return the international dialing prefix (e.g. '+234' for NG)."""
    loc = _loc_from_context(context)
    return str(loc.get("dial_code") or "")


@register.simple_tag(takes_context=True, name="local_postal_label")
def local_postal_label(context) -> str:
    """Return the user-friendly postal-code field label (ZIP/PIN/CEP/...)."""
    loc = _loc_from_context(context)
    return str(loc.get("postal_code_label") or "Postal code")


@register.simple_tag(takes_context=True, name="local_region_label")
def local_region_label(context) -> str:
    """Return the localized first-level subdivision label (State/Province/...)."""
    loc = _loc_from_context(context)
    return str(loc.get("region_label") or "Region")


@register.simple_tag(takes_context=True, name="local_address_order")
def local_address_order(context) -> list:
    """Return the country's ordered list of address-field keys.

    Usage:
        {% local_address_order as fields %}
        {% for key in fields %}
            <input name="{{ key }}" placeholder="{{ key }}">
        {% endfor %}
    """
    loc = _loc_from_context(context)
    order = loc.get("address_order")
    if isinstance(order, list):
        return order
    return ["street", "city", "region", "postal_code", "country"]


@register.simple_tag(takes_context=True, name="local_language_code")
def local_language_code(context) -> str:
    """Wave 6: return the user's effective language BCP-47 code (or "")."""
    loc = _loc_from_context(context)
    return str(loc.get("language_code") or "")


@register.simple_tag(takes_context=True, name="local_language_native")
def local_language_native(context) -> str:
    """Wave 6: return the user's effective language native name (or "")."""
    loc = _loc_from_context(context)
    return str(loc.get("language_native") or "")


@register.simple_tag(takes_context=True, name="local_system_name")
def local_system_name(context) -> str:
    """Wave 6: return the per-language education-system name when set.

    For multilingual countries this carries the per-language overlay's
    `system_name` (e.g. "French / Baccalauréat Subsystem" for CM-FR,
    "British / GCE O & A Level Subsystem" for CM-EN). Empty string when
    the user is on a monolingual country or the country baseline.
    """
    loc = _loc_from_context(context)
    return str(loc.get("system_name") or "")


@register.simple_tag(takes_context=True, name="local_name_order")
def local_name_order(context) -> str:
    """Return either 'given-family' (Western) or 'family-given' (Eastern)."""
    loc = _loc_from_context(context)
    return str(loc.get("name_order") or "given-family")
