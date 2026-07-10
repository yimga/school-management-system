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
import os
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
    mapped = DEFAULT_REGION_BY_COUNTRY.get(code)
    if mapped is None:
        # No static map entry and no RuntimeDefaults override. Falling back
        # to the global region is safe by default, but for a real country
        # code this may breach a data-residency requirement the operator
        # hasn't configured yet — surface it instead of swallowing it.
        logger.warning(
            "data_residency: no region mapping for country=%s; defaulting to %s "
            "(add an override in RuntimeDefaults['data_residency.country_overrides'])",
            code,
            GLOBAL_DATA_REGION,
        )
        return GLOBAL_DATA_REGION
    return mapped


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


def default_store_region() -> str:
    """Declared region of the DEFAULT database (env-or-setting, default global).

    The default store is where every op lands when no per-region alias
    resolves. Historically that landing was invisible to the border lock (the
    router early-returned on a missing alias); declaring the default store's
    region makes the unresolvable-region case *comparable* — in-region tenants
    keep working, tenants with a foreign residency promise fail closed under
    enforcement. ``"global"`` matches the platform model the readiness
    preflight already codifies (global is served by the default DB by
    definition); a deployment whose primary physically sits in a specific
    region declares it via ``DATA_RESIDENCY_DEFAULT_STORE_REGION`` (env wins
    over the Django setting so an ops flip needs no redeploy).
    """
    raw = (os.environ.get("DATA_RESIDENCY_DEFAULT_STORE_REGION", "") or "").strip().lower()
    if raw:
        return raw
    from django.conf import settings

    explicit = (
        str(getattr(settings, "DATA_RESIDENCY_DEFAULT_STORE_REGION", "") or "")
        .strip()
        .lower()
    )
    return explicit or GLOBAL_DATA_REGION


def region_for_alias(alias: Any) -> str:
    """Map a ``DATABASES`` alias to the region it serves.

    The platform has exactly two alias-naming conventions the border lock
    must understand: ``replica_<region>`` (the Wave-K4 env registration —
    ``DATA_RESIDENCY_REPLICA_<REGION>``) and region-named aliases (the
    ``regional_cluster`` convention). A missing/blank alias and the literal
    ``default`` alias both mean the op is served by the default store, whose
    region is :func:`default_store_region`. Everything else is passed through
    as region-named, so an alias the platform cannot map to a region compares
    unequal and fails closed under enforcement rather than passing unseen.
    """
    name = str(alias or "").strip().lower()
    if not name or name == "default":
        return default_store_region()
    if name.startswith("replica_"):
        return name[len("replica_"):] or default_store_region()
    return name


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

    Called from request middleware once cross-region routing is live; raises
    when enforcement is on (env-or-setting via the compliance
    ``residency_enforced`` contract, so an ops env flip binds here too).

    Two arms (2026-07-09 unresolvable-region closeout):

    * **Blank operational binding** — the request is being SERVED from the
      default store. Historically treated as aligned ("no promise broken
      yet"), which under enforcement was fail-open for tenants with a foreign
      residency promise. Now delegated to the hard gate, which compares the
      school's effective region against the DECLARED default-store region
      (:func:`default_store_region`) and raises the typed, audited
      ``ResidencyViolation`` on mismatch. No-op when enforcement is off, so
      the soft posture (and ``is_aligned``'s documented semantics, which the
      verify command keeps) is unchanged.
    * **Populated-but-mismatched binding** — unchanged contract:
      ``CrossRegionWriteError`` under enforcement, warning otherwise.
    """
    if school is None:
        return
    operational = (getattr(school, "regional_cluster", "") or "").strip()
    if not operational:
        from apps.compliance.cross_border_export import enforce_region_match

        enforce_region_match(school, default_store_region(), kind="db_route")
        return
    reg = effective_region(school)
    if operational == reg:
        return
    from apps.compliance.cross_border_export import residency_enforced

    msg = f"data residency mismatch school={getattr(school, 'slug', '?')} operational={operational} regulatory={reg}"
    if residency_enforced():
        raise CrossRegionWriteError(msg)
    logger.warning(msg)


__all__ = [
    "CANONICAL_REGIONS",
    "CrossRegionWriteError",
    "DEFAULT_REGION_BY_COUNTRY",
    "assert_aligned_or_log",
    "default_store_region",
    "derive_default_region",
    "effective_region",
    "is_aligned",
    "is_canonical",
    "region_for_alias",
]
