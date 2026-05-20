"""Wave E — G4: data residency derivation + alignment checks.

Adds an explicit ``School.data_region`` field (regulatory answer) on top
of the existing ``School.regional_cluster`` (operational DB-alias answer)
plus helpers that:

* derive the right region from ``country_code`` when not explicitly set;
* assert that the request-time DB alias matches the tenant's expected
  region (logged, not raised, so the request still succeeds — the
  alignment check is enforcement-by-audit, not by exception);
* support the ``verify_data_residency`` management command.

Why two fields: deploying a region-aware Postgres replica is a deploy /
ops decision (operational), while *requiring* a tenant's data to stay
in-region is a legal / compliance decision (regulatory). They can be the
same value 99% of the time; the gap matters during transitions (we
provision a new region, want to flip tenants gradually).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Canonical region codes the platform recognises. Operators may seed
# additional values via `RuntimeDefaults.payload["data_residency.regions"]`
# without touching code, but the audit trail prefers the canonical set.
# Default region when no country mapping exists; served by the primary DB (no replica).
GLOBAL_DATA_REGION: str = "global"

CANONICAL_REGIONS: frozenset[str] = frozenset({
    "us_east",
    "us_west",
    "eu_central",
    "eu_west",
    "uk",
    "apac_southeast",
    "apac_southwest",
    "apac_northeast",
    "afr_west",
    "afr_south",
    "latam_south",
    "global",
})


# Country → default region map. Operators override via RuntimeDefaults
# payload at deploy time; this constant is the no-config fallback.
DEFAULT_REGION_BY_COUNTRY: dict[str, str] = {
    # Europe (GDPR)
    "DE": "eu_central", "FR": "eu_central", "NL": "eu_central",
    "BE": "eu_central", "AT": "eu_central", "CH": "eu_central",
    "PL": "eu_central", "CZ": "eu_central", "IT": "eu_west",
    "ES": "eu_west", "PT": "eu_west", "IE": "eu_west",
    "SE": "eu_west", "DK": "eu_west", "NO": "eu_west", "FI": "eu_west",
    "GB": "uk",
    # Americas
    "US": "us_east", "CA": "us_east", "MX": "us_east",
    "BR": "latam_south", "AR": "latam_south", "CL": "latam_south",
    "CO": "latam_south", "PE": "latam_south",
    # APAC
    "JP": "apac_northeast", "KR": "apac_northeast", "TW": "apac_northeast",
    "CN": "apac_northeast", "HK": "apac_northeast",
    "IN": "apac_southwest", "PK": "apac_southwest",
    "SG": "apac_southeast", "MY": "apac_southeast", "ID": "apac_southeast",
    "TH": "apac_southeast", "PH": "apac_southeast", "VN": "apac_southeast",
    "AU": "apac_southeast", "NZ": "apac_southeast",
    # Africa
    "NG": "afr_west", "GH": "afr_west", "CM": "afr_west", "SN": "afr_west",
    "CI": "afr_west", "ZA": "afr_south", "KE": "afr_west", "EG": "afr_west",
}


def derive_default_region(country_code: str) -> str:
    """Resolve the default region for a country.

    Reads ``RuntimeDefaults.payload["data_residency.country_overrides"]``
    first; falls back to ``DEFAULT_REGION_BY_COUNTRY``; returns ``"global"``
    when no mapping exists.
    """
    code = (country_code or "").strip().upper()
    if not code:
        return GLOBAL_DATA_REGION
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        row = RuntimeDefaults.objects.order_by("pk").first()
        if row is not None:
            payload = getattr(row, "payload", None) or {}
            overrides = payload.get("data_residency.country_overrides")
            if isinstance(overrides, dict):
                explicit = overrides.get(code)
                if isinstance(explicit, str) and explicit.strip():
                    return explicit.strip()
    except (ImportError, RuntimeError, AttributeError, ValueError):
        pass
    return DEFAULT_REGION_BY_COUNTRY.get(code, GLOBAL_DATA_REGION)


def effective_region(school: Any) -> str:
    """Return the school's effective data residency region.

    Explicit ``School.data_region`` wins; otherwise derived from
    ``country_code``. Schools with neither default to ``"global"``.
    """
    if school is None:
        return "global"
    explicit = (getattr(school, "data_region", "") or "").strip()
    if explicit:
        return explicit
    return derive_default_region(getattr(school, "country_code", "") or "")


def is_canonical(region: str) -> bool:
    """Whether ``region`` is in the canonical set."""
    return region in CANONICAL_REGIONS


def is_aligned(school: Any) -> bool:
    """Return True if the school's operational DB alias matches its data region.

    The check uses ``School.regional_cluster`` (operational) vs
    ``effective_region(school)`` (regulatory). When ``regional_cluster``
    is blank, we treat the school as "default cluster" and only the
    regulatory side is examined — alignment is technically true (no
    promise has been broken yet), but the verify command will warn.
    """
    if school is None:
        return True
    operational = (getattr(school, "regional_cluster", "") or "").strip()
    if not operational:
        return True  # no operational binding yet; verify cmd will flag this
    return operational == effective_region(school)


class CrossRegionWriteError(RuntimeError):
    """Raised by hardening hooks when a write resolves to a non-matching region.

    Not raised today inside the request path (would break tenants whose
    operational alias has not been provisioned yet); reserved for the
    hardening pass that flips ``settings.DATA_RESIDENCY_ENFORCE = True``.
    """


def assert_aligned_or_log(school: Any) -> None:
    """Soft enforcement: log a warning when alignment is broken.

    Called from request middleware once cross-region routing is live;
    flips to raising ``CrossRegionWriteError`` when
    ``settings.DATA_RESIDENCY_ENFORCE`` is True.
    """
    if school is None:
        return
    if is_aligned(school):
        return
    from django.conf import settings

    op = (getattr(school, "regional_cluster", "") or "").strip()
    reg = effective_region(school)
    msg = f"data residency mismatch school={getattr(school, 'slug', '?')} operational={op} regulatory={reg}"
    if getattr(settings, "DATA_RESIDENCY_ENFORCE", False):
        raise CrossRegionWriteError(msg)
    logger.warning(msg)


__all__ = [
    "CANONICAL_REGIONS",
    "CrossRegionWriteError",
    "DEFAULT_REGION_BY_COUNTRY",
    "assert_aligned_or_log",
    "derive_default_region",
    "effective_region",
    "is_aligned",
    "is_canonical",
]
