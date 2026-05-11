"""
Part F Section 25.1: Tax engine — regional tax (VAT/GST) computation from policy/settings.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional


# Fallback table covering common jurisdictions. Authoritative rates should live in
# RegionConfig / ComplianceProfile (per-tenant) and override this table via `rate_override`
# or by looking up the country profile before calling. This table is intentionally not
# exhaustive — countries not listed here resolve to a rate of 0, and the caller is
# expected to log a warning so the missing jurisdiction can be added or registered in
# the tenant's compliance profile.
DEFAULT_REGIONAL_RATES: dict[tuple[str, str], Decimal] = {
    ("US", "VAT"): Decimal("0"),  # No federal VAT; state sales tax handled separately
    ("GB", "VAT"): Decimal("0.20"),
    ("DE", "VAT"): Decimal("0.19"),
    ("FR", "VAT"): Decimal("0.20"),
    ("ES", "VAT"): Decimal("0.21"),
    ("IT", "VAT"): Decimal("0.22"),
    ("NL", "VAT"): Decimal("0.21"),
    ("BE", "VAT"): Decimal("0.21"),
    ("CH", "VAT"): Decimal("0.077"),
    ("AT", "VAT"): Decimal("0.20"),
    ("IE", "VAT"): Decimal("0.23"),
    ("SE", "VAT"): Decimal("0.25"),
    ("NO", "VAT"): Decimal("0.25"),
    ("DK", "VAT"): Decimal("0.25"),
    ("FI", "VAT"): Decimal("0.24"),
    ("PT", "VAT"): Decimal("0.23"),
    ("PL", "VAT"): Decimal("0.23"),
    ("CM", "VAT"): Decimal("0.195"),
    ("NG", "VAT"): Decimal("0.075"),
    ("ZA", "VAT"): Decimal("0.15"),
    ("KE", "VAT"): Decimal("0.16"),
    ("GH", "VAT"): Decimal("0.15"),
    ("EG", "VAT"): Decimal("0.14"),
    ("MA", "VAT"): Decimal("0.20"),
    ("TN", "VAT"): Decimal("0.19"),
    ("AE", "VAT"): Decimal("0.05"),
    ("SA", "VAT"): Decimal("0.15"),
    ("CA", "GST"): Decimal("0.05"),
    ("MX", "VAT"): Decimal("0.16"),
    ("BR", "VAT"): Decimal("0.17"),
    ("AR", "VAT"): Decimal("0.21"),
    ("CL", "VAT"): Decimal("0.19"),
    ("CO", "VAT"): Decimal("0.19"),
    ("JP", "VAT"): Decimal("0.10"),
    ("CN", "VAT"): Decimal("0.13"),
    ("KR", "VAT"): Decimal("0.10"),
    ("IN", "GST"): Decimal("0.18"),
    ("SG", "GST"): Decimal("0.09"),
    ("AU", "GST"): Decimal("0.10"),
    ("NZ", "GST"): Decimal("0.15"),
    ("ID", "VAT"): Decimal("0.11"),
    ("PH", "VAT"): Decimal("0.12"),
    ("TH", "VAT"): Decimal("0.07"),
    ("VN", "VAT"): Decimal("0.10"),
    ("MY", "GST"): Decimal("0.06"),
    ("TR", "VAT"): Decimal("0.18"),
}


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

    For tenant accuracy, callers should resolve the rate from the school's ComplianceProfile
    (or RegionConfig) before calling this function and pass it as ``rate_override``. The
    fallback table below is a best-effort approximation for jurisdictions that have not
    yet been registered in the tenant's compliance profile; unknown jurisdictions
    resolve to zero (which is intentionally conservative — better to under-charge tax
    than to silently invent one).
    """
    if rate_override is not None:
        return (amount * rate_override).quantize(Decimal("0.01"))
    key = (region_code.upper()[:2], tax_type.upper())
    rate = DEFAULT_REGIONAL_RATES.get(key, Decimal("0"))
    return (amount * rate).quantize(Decimal("0.01"))
