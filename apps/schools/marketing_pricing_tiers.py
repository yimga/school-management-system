"""Published, INDICATIVE pricing tiers for the marketing site.

Transparency lever (competitors like Gradelink/Brightwheel publish pricing; we
gate behind a demo). To stay honest we do NOT invent prices: the per-student
figures here are derived from the SAME illustrative module constants the
on-page entitlement calculator already uses —

    static/marketing/js/mkt-entitlement-calculator.js
        BASE = { transport: 4, grading: 6, comms: 3, billing: 8 }
        (USD / student / month, labelled "Indicative tier" in the calculator)

Every tier is explicitly marked INDICATIVE and points to the interactive
calculator / a quote for an exact figure. Currency-aware symbol only; we do not
fabricate FX conversions (the figure stays the indicative USD-derived number
with the local symbol, matching the calculator's own behaviour).
"""

from __future__ import annotations

from typing import TypedDict

# Mirror of the entitlement-calculator module costs (USD/student/month).
_MODULE_COST: dict[str, int] = {"transport": 4, "grading": 6, "comms": 3, "billing": 8}

# Currency symbols (mirrors SYMBOLS in mkt-entitlement-calculator.js intent).
_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "GBP": "£",
    "EUR": "€",
    "NGN": "₦",
    "KES": "KSh ",
    "GHS": "GH₵ ",
    "INR": "₹",
    "ZAR": "R ",
    "BRL": "R$ ",
    "SAR": "SAR ",
    "AED": "AED ",
}


class PricingTier(TypedDict):
    """One indicative published tier."""

    key: str
    name: str
    indicative_from: int            # USD-derived per-student/month figure
    price_note: str                 # rendered caption (currency-aware)
    is_custom: bool                 # Enterprise = contact for a quote
    who_for: str
    included: list[str]
    cta_label: str
    cta_route: str                  # url name
    indicative: bool                # always True — never a contractual quote


def _symbol(currency: str) -> str:
    return _SYMBOLS.get((currency or "USD").upper(), (currency or "USD").upper() + " ")


def pricing_tiers(currency: str = "USD") -> list[PricingTier]:
    """Three indicative tiers derived from the calculator's module constants.

    Starter  = a single core module (comms)            -> from $3
    Growth   = comms + grading + billing               -> from $17
    Enterprise = everything + multi-campus, custom      -> contact for a quote
    """

    cur = (currency or "USD").upper()
    sym = _symbol(cur)
    starter = _MODULE_COST["comms"]                                   # 3
    growth = _MODULE_COST["comms"] + _MODULE_COST["grading"] + _MODULE_COST["billing"]  # 17

    def note(amount: int) -> str:
        return f"from {sym}{amount} / student / month · indicative"

    return [
        {
            "key": "starter",
            "name": "Starter",
            "indicative_from": starter,
            "price_note": note(starter),
            "is_custom": False,
            "who_for": "Single-campus schools getting the essentials online.",
            "included": [
                "Admissions, student records & attendance",
                "Parent communications (email / SMS / WhatsApp where available)",
                "Parent & student portals",
                "Offline-first PWA",
            ],
            "cta_label": "Start with a demo",
            "cta_route": "marketing_demo",
            "indicative": True,
        },
        {
            "key": "growth",
            "name": "Growth",
            "indicative_from": growth,
            "price_note": note(growth),
            "is_custom": False,
            "who_for": "Schools adding finance, grading and richer engagement.",
            "included": [
                "Everything in Starter",
                "Fees & payments (mobile-money + card rails)",
                "Grading & report cards",
                "Analytics & workflows",
            ],
            "cta_label": "See a tailored estimate",
            "cta_route": "marketing_pricing",
            "indicative": True,
        },
        {
            "key": "enterprise",
            "name": "Enterprise",
            "indicative_from": 0,
            "price_note": "Custom · let's talk",
            "is_custom": True,
            "who_for": "Networks, districts and ministries running many campuses.",
            "included": [
                "Everything in Growth",
                "Multi-campus / district control plane",
                "Migration, SSO, API & webhooks",
                "Governance, compliance & dedicated support",
            ],
            "cta_label": "Talk to us",
            "cta_route": "marketing_demo",
            "indicative": True,
        },
    ]
