"""
Single source of truth for currency codes and symbols (platform layer).
Used by context_processors, reports, evals/grading, translations, and geoip_service.
Moved from siteconfig as part of platform decomposition; siteconfig.currency re-exports for backward compatibility.
"""

# Canonical map: ISO 4217 currency code -> display symbol
CURRENCY_SYMBOLS = {
    "XAF": "FCFA",  # Cameroon / CEMAC
    "XOF": "CFA",  # West Africa / UEMOA
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "KES": "Ksh",  # Kenya
    "NGN": "₦",  # Nigeria
    "ZAR": "R",  # South Africa
    "GHS": "GH₵",  # Ghana
    "TZS": "TSh",  # Tanzania
    "UGX": "USh",  # Uganda
    "RWF": "FRw",  # Rwanda
    "EGP": "E£",  # Egypt
}


# Lazily-loaded mirror of CurrencyRegistry.symbol (ISO 4217 -> symbol) so the
# ~250-currency footprint resolves to real glyphs (฿, ₫, ₲, …) instead of bare
# codes, without a DB hit on the hot path for the curated common currencies above.
# Sentinel-cached: only a NON-empty load is cached, so it self-heals once the DB /
# registry is available (never permanently caches an empty result at import time).
_REGISTRY_SYMBOLS_CACHE: dict[str, str] | None = None


def _registry_symbols() -> dict[str, str]:
    global _REGISTRY_SYMBOLS_CACHE
    if _REGISTRY_SYMBOLS_CACHE is not None:
        return _REGISTRY_SYMBOLS_CACHE
    try:
        from apps.registries.models import CurrencyRegistry

        loaded = {
            str(code).upper(): str(symbol)
            for code, symbol in CurrencyRegistry.objects.filter(is_active=True)
            .exclude(symbol="")
            .values_list("code", "symbol")
            if symbol
        }
    except Exception:  # noqa: BLE001 - display helper must never raise (DB not ready, etc.)
        return {}
    if loaded:
        _REGISTRY_SYMBOLS_CACHE = loaded
    return loaded


def get_currency_symbol(currency_code: str) -> str:
    """Return display symbol for a currency code. Falls back to code if unknown.

    Resolution order: curated platform map (fast, curated forms like FCFA/Ksh win)
    -> CurrencyRegistry (DB, ~250 currencies) -> the bare ISO code.
    """
    if not currency_code:
        return ""
    code = currency_code.upper()
    curated = CURRENCY_SYMBOLS.get(code)
    if curated:
        return curated
    return _registry_symbols().get(code, code)


# ── ISO 4217 minor units + symbol convention ────────────────────────────────
# Reference data (same nature as CURRENCY_SYMBOLS above): the number of fractional
# digits a currency's minor unit uses. The overwhelming majority use 2; the sets
# below are the real-world exceptions. XAF/XOF — the CFA franc (Cameroon/CEMAC and
# West Africa) — have NO minor unit, which is exactly why school fees must render
# "50 000 FCFA", never "FCFA50,000.00".
_ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG",
        "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
    }
)
_THREE_DECIMAL_CURRENCIES = frozenset(
    {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}
)
# Currencies whose symbol is written AFTER the amount with a (non-breaking) space,
# in every locale that uses them: the CFA franc (Central + West Africa) and the CFP
# franc (Pacific). "50 000 FCFA", not "FCFA50 000". This is a property of the
# currency, not of the tenant's separator configuration.
_SUFFIX_SPACE_CURRENCIES = frozenset({"XAF", "XOF", "XPF"})

_NBSP = " "

_REGISTRY_DECIMALS_CACHE: "dict[str, int] | None" = None


def _registry_decimal_places() -> dict:
    """Lazy sentinel-cached mirror of ``CurrencyRegistry.decimal_places`` (DB SoT).

    Consulted only for currencies outside the static tables above. Mirrors
    ``_registry_symbols``: never raises (DB may not be ready) and only caches a
    non-empty load, so it self-heals once the registry is populated.
    """
    global _REGISTRY_DECIMALS_CACHE
    if _REGISTRY_DECIMALS_CACHE is not None:
        return _REGISTRY_DECIMALS_CACHE
    try:
        from apps.registries.models import CurrencyRegistry

        loaded = {
            str(code).upper(): int(dp)
            for code, dp in CurrencyRegistry.objects.filter(is_active=True).values_list(
                "code", "decimal_places"
            )
            if dp is not None
        }
    except Exception:  # noqa: BLE001 - display helper must never raise
        return {}
    if loaded:
        _REGISTRY_DECIMALS_CACHE = loaded
    return loaded


def get_currency_decimal_places(currency_code: str) -> int:
    """Fractional digit count for a currency (ISO 4217 minor units).

    Static reference for the common currencies + exceptions, then the DB registry
    for the long tail, then the ISO default of 2. Returns 0 for the CFA franc, JPY,
    etc. — the whole reason fee amounts were rendering with two bogus decimals.
    """
    code = (currency_code or "").upper()
    if not code:
        return 2
    if code in _ZERO_DECIMAL_CURRENCIES:
        return 0
    if code in _THREE_DECIMAL_CURRENCIES:
        return 3
    dp = _registry_decimal_places().get(code)
    return dp if dp is not None else 2


def format_money(
    amount,
    currency_code,
    *,
    symbol=None,
    decimal_sep=None,
    thousands_sep=None,
) -> str:
    """Render a monetary amount for display with the currency's real conventions.

    The single formatter every tenant-facing money surface should route through
    (invoices, receipts, statements, report cards). It honours the currency's
    minor-unit digit count (``get_currency_decimal_places``) and symbol placement.

    ``decimal_sep`` / ``thousands_sep`` let a locale-configured tenant override the
    grouping; when omitted, per-currency defaults apply. The CFA / CFP franc always
    renders space-grouped, zero-decimal, and symbol-suffixed ("50 000 FCFA")
    regardless of separator config — that is a property of the currency itself.
    """
    if amount is None:
        return ""
    code = (currency_code or "").upper()
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    if symbol is None:
        symbol = get_currency_symbol(code)
    decimals = get_currency_decimal_places(code)
    suffix = code in _SUFFIX_SPACE_CURRENCIES
    if suffix:
        group, dec = _NBSP, ","
    else:
        group = thousands_sep if thousands_sep is not None else ","
        dec = decimal_sep if decimal_sep is not None else "."
    body = (
        f"{amt:,.{decimals}f}".replace(",", "\x00").replace(".", dec).replace("\x00", group)
    )
    if not symbol:
        return body
    if suffix:
        return f"{body}{_NBSP}{symbol}"
    return f"{symbol}{body}"
