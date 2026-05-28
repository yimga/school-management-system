"""Regional surface vocabulary for operator UI (0% hardcoded template strings)."""

from __future__ import annotations

from typing import Any

# ISO2 country → token → localized operator label
REGIONAL_SURFACE_REGISTRY: dict[str, dict[str, str]] = {
    "US": {
        "txt_compliance_hub": "State compliance tracker",
        "txt_governing_gateway": "District data gateway",
        "txt_invoicing_hub": "ACH & card invoicing hub",
    },
    "GB": {
        "txt_compliance_hub": "Ofsted compliance tracker",
        "txt_governing_gateway": "DfE gateway link",
        "txt_invoicing_hub": "Academy trust invoicing hub",
    },
    "SA": {
        "txt_compliance_hub": "MoE compliance tracker",
        "txt_governing_gateway": "ZATCA invoicing hub",
        "txt_invoicing_hub": "SAR payment rails hub",
    },
    "ID": {
        "txt_compliance_hub": "Dapodik gateway link",
        "txt_governing_gateway": "Ministry integration portal",
        "txt_invoicing_hub": "National billing hub",
    },
    "NG": {
        "txt_compliance_hub": "UBEC reporting tracker",
        "txt_governing_gateway": "State ministry gateway",
        "txt_invoicing_hub": "Family billing hub",
    },
}


def _country_code(context: dict[str, Any] | None) -> str:
    ctx = context or {}
    req = ctx.get("request")
    geo = getattr(req, "geo_context", None) if req is not None else None
    if isinstance(geo, dict) and geo.get("country_code"):
        return str(geo["country_code"]).upper()
    brand = ctx.get("brand") or {}
    if isinstance(brand, dict) and brand.get("country_code"):
        return str(brand["country_code"]).upper()
    school = ctx.get("school") or getattr(req, "school", None)
    if school is not None:
        cc = getattr(school, "country_code", None) or getattr(school, "country", None)
        if cc:
            return str(cc).upper()[:2]
    return "US"


def regional_surface_token(context: dict[str, Any] | None, token: str) -> str | None:
    cc = _country_code(context)
    registry = REGIONAL_SURFACE_REGISTRY.get(cc) or REGIONAL_SURFACE_REGISTRY["US"]
    return registry.get(token)
