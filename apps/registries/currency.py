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


def get_currency_symbol(currency_code: str) -> str:
    """Return display symbol for a currency code. Falls back to code if unknown."""
    if not currency_code:
        return ""
    return CURRENCY_SYMBOLS.get(currency_code.upper(), currency_code)
