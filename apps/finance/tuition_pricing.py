"""Apply PPP multipliers to tenant tuition fee lines (opt-in per school)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.finance.models import FeeItem


def tuition_ppp_enabled_for_school(school: Any | None) -> bool:
    """Tenant opt-in via ``school.settings['finance_apply_ppp_to_tuition']``."""
    if school is None:
        return False
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        return False
    return bool(settings.get("finance_apply_ppp_to_tuition", False))


def _country_code_for_school(school: Any) -> str:
    code = (
        getattr(school, "country_code", None)
        or getattr(getattr(school, "default_region", None), "code", None)
        or "US"
    )
    raw = str(code).strip().upper()
    if len(raw) == 3:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        alpha2 = GlobalGeoCatalog.alpha2_for_country(raw)
        if alpha2:
            return alpha2
    return raw[:2] if raw else "US"


def localized_tuition_amount(
    *,
    school: Any | None,
    base_amount: Decimal | str | int | float,
    item_type: str,
) -> Decimal:
    """Return PPP-adjusted tuition subtotal when enabled; other fee types unchanged."""
    amount = Decimal(str(base_amount))
    if school is None or item_type != FeeItem.ItemType.TUITION:
        return amount
    if not tuition_ppp_enabled_for_school(school):
        return amount
    from apps.billing.regional_pricing import compute_localized_price

    localized = compute_localized_price(amount, _country_code_for_school(school))
    return localized.subtotal
