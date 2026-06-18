"""Marketplace PPP pricing — uses in-repo ``billing.regional_pricing`` (no external API)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def apply_ppp_to_storefront(*, school: Any, base_usd: Decimal | str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from apps.billing.regional_pricing import compute_localized_price

    cc = (
        (payload or {}).get("settlement_country")
        or getattr(school, "country_code", None)
        or "US"
    )
    localized = compute_localized_price(base_usd, str(cc).strip().upper())
    record = {
        "country_code": localized.country_code,
        "currency_code": localized.currency_code,
        "multiplier": str(localized.multiplier),
        "tax_rate": str(localized.tax_rate),
        "subtotal": str(localized.subtotal),
        "tax": str(localized.tax),
        "total": str(localized.total),
        "engine": "billing.regional_pricing",
    }
    settings = dict(getattr(school, "settings", None) or {})
    mp = dict(settings.get("marketplace_ppp") or {})
    mp["last_localized_price"] = record
    settings["marketplace_ppp"] = mp
    school.settings = settings
    school.save(update_fields=["settings"])
    return record
