"""
Part F Section 25.1: Tax engine — regional tax (VAT/GST) computation from policy/settings.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional


def compute_tax(
    amount: Decimal,
    region_code: str,
    tax_type: str = "VAT",
    *,
    rate_override: Optional[Decimal] = None,
) -> Decimal:
    """
    Compute tax for a given amount and region (Part F 16.1 regional tax, 25.1 tax engine).
    Rate comes from policy/settings by region; rate_override allows caller to pass a rate.
    """
    if rate_override is not None:
        return (amount * rate_override).quantize(Decimal("0.01"))
    # Default regional rates (can be moved to policy/CurrencyRegistry/RegionConfig)
    _regional_rates: dict[tuple[str, str], Decimal] = {
        ("US", "VAT"): Decimal("0"),  # No federal VAT; state varies
        ("GB", "VAT"): Decimal("0.20"),
        ("DE", "VAT"): Decimal("0.19"),
        ("FR", "VAT"): Decimal("0.20"),
        ("CM", "VAT"): Decimal("0.195"),  # Cameroon
        ("NG", "VAT"): Decimal("0.075"),
        ("AE", "VAT"): Decimal("0.05"),
        ("CA", "GST"): Decimal("0.05"),
        ("BR", "VAT"): Decimal("0.17"),  # ICMS varies by state
        ("JP", "VAT"): Decimal("0.10"),
    }
    key = (region_code.upper()[:2], tax_type.upper())
    rate = _regional_rates.get(key, Decimal("0"))
    return (amount * rate).quantize(Decimal("0.01"))
