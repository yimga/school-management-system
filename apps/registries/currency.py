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
