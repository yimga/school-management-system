"""Phase 6 turbo runtime: regulator API federation broker.

Defines the broker contract over which live regulator APIs (X-Road, DigiLocker,
GIAS, NCES, MOE, NAFATH, SACE) plug in. Each adapter ships its own credentials
via env; the broker itself is stateless and routes by country + capability.

Live credentials are EXTERNAL_BLOCKED on the operator_signoff allowlist until
the broker is provisioned in a residency region.
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-regulator-api-federation"
CONTRACT_TITLE = "Regulator API federation broker"


ADAPTER_REGISTRY: dict[str, dict[str, Any]] = {
    "EE": {"adapter": "x_road", "capabilities": ("student_records", "identity")},
    "IN": {"adapter": "digilocker", "capabilities": ("academic_credential", "identity_kyc")},
    "GB": {"adapter": "gias", "capabilities": ("school_metadata", "urn")},
    "US": {"adapter": "nces", "capabilities": ("district_directory", "school_directory")},
    "SG": {"adapter": "moe_singapore", "capabilities": ("school_directory",)},
    "SA": {"adapter": "nafath", "capabilities": ("identity",)},
    "ZA": {"adapter": "sace", "capabilities": ("educator_registration",)},
}


class RegulatorAdapterUnavailable(RuntimeError):
    """Raised when an adapter is registered but not provisioned with credentials."""


def supported_countries() -> list[str]:
    return sorted(ADAPTER_REGISTRY.keys())


def lookup(country_iso: str, capability: str) -> dict[str, Any]:
    entry = ADAPTER_REGISTRY.get(country_iso.upper())
    if entry is None:
        return {"available": False, "reason": "no_adapter_for_country", "country_iso": country_iso}
    if capability not in entry["capabilities"]:
        return {"available": False, "reason": "capability_not_supported", "country_iso": country_iso, "capability": capability}
    return {
        "available": True,
        "adapter": entry["adapter"],
        "country_iso": country_iso.upper(),
        "capability": capability,
        "credentials_status": "EXTERNAL_BLOCKED_operator_signoff",
    }


def call(country_iso: str, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = lookup(country_iso, capability)
    if not result.get("available"):
        return result
    if result.get("credentials_status", "").startswith("EXTERNAL_BLOCKED"):
        raise RegulatorAdapterUnavailable(f"{result['adapter']}:credentials_not_provisioned")
    return {"adapter": result["adapter"], "country_iso": country_iso, "capability": capability, "request_payload": payload}


def runtime_health() -> dict[str, Any]:
    sample = lookup("GB", "school_metadata")
    return {"contract_id": CONTRACT_ID, "healthy": sample.get("available"), "supported_countries": supported_countries()}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "broker_present_credentials_external_blocked" if h.get("healthy") else "scaffold_only", "runtime_health": h}
