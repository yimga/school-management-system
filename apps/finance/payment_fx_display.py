"""Settlement currency visibility without hidden FX conversion (SFDP 1469)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def settlement_display_for_profile(profile: dict[str, Any] | None, amount: Decimal | str) -> dict[str, str]:
    if not profile:
        return {"display": str(amount), "settlement_currency": "", "fx_disclaimer": ""}
    settlement = str(profile.get("settlement_currency") or profile.get("currency") or "")
    display_currency = str(profile.get("currency") or settlement)
    amt = amount if isinstance(amount, Decimal) else Decimal(str(amount or "0"))
    minor = int(profile.get("minor_units") or 2)
    formatted = f"{amt:.{minor}f} {display_currency}"
    disclaimer = ""
    if settlement and settlement != display_currency:
        disclaimer = (
            f"Settlement may occur in {settlement}; displayed amount is invoice currency — "
            "no hidden conversion applied."
        )
    return {
        "display": formatted,
        "settlement_currency": settlement,
        "invoice_currency": display_currency,
        "fx_disclaimer": disclaimer,
    }
