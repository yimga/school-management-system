"""Continent-level governance archetype defaults for global governance matrix enrichment.

Used when a country row has no country-specific governance override yet (Phase 0C
locale pass may apply these before GEO completes full dissection).
"""

from __future__ import annotations

from typing import Any

from lib.global_governance_geo import is_likely_territory

ARCHETYPES = frozenset(
    {
        "single_org_multi_site",
        "district_trust_overlay",
        "federation_equals",
        "state_emis_hub",
    }
)

# Default governance patterns per continent (plan §0.4 — defaults only, not replacements).
CONTINENT_ARCHETYPE_DEFAULTS: dict[str, dict[str, Any]] = {
    "Africa": {
        "governance_archetype": "state_emis_hub",
        "employer_model": "state",
        "reporting_chain": ["school", "lga", "state", "federal"],
        "recommended_operating_mode": "standalone",
        "school_structure": "both_common",
        "ownership_types": ["public", "private", "faith", "ngo"],
    },
    "Asia": {
        "governance_archetype": "state_emis_hub",
        "employer_model": "state",
        "reporting_chain": ["school", "ministry"],
        "recommended_operating_mode": "standalone",
        "school_structure": "both_common",
        "ownership_types": ["public", "private", "international"],
    },
    "Europe": {
        "governance_archetype": "state_emis_hub",
        "employer_model": "state",
        "reporting_chain": ["school", "authority", "ministry"],
        "recommended_operating_mode": "group_common",
        "school_structure": "both_common",
        "ownership_types": ["public", "private", "faith"],
    },
    "Americas": {
        "governance_archetype": "district_trust_overlay",
        "employer_model": "district",
        "reporting_chain": ["school", "district", "state"],
        "recommended_operating_mode": "standalone",
        "school_structure": "both_common",
        "ownership_types": ["public", "private", "charter"],
    },
    "Oceania": {
        "governance_archetype": "district_trust_overlay",
        "employer_model": "state",
        "reporting_chain": ["school", "state", "federal"],
        "recommended_operating_mode": "standalone",
        "school_structure": "both_common",
        "ownership_types": ["public", "private", "faith"],
    },
    "Antarctica": {
        "governance_archetype": "single_org_multi_site",
        "employer_model": "school",
        "reporting_chain": ["school"],
        "recommended_operating_mode": "standalone",
        "school_structure": "single_tenant_campuses",
        "ownership_types": ["public"],
    },
    "Territories": {
        "governance_archetype": "district_trust_overlay",
        "employer_model": "school",
        "reporting_chain": ["school", "parent_sovereign"],
        "recommended_operating_mode": "standalone",
        "school_structure": "single_tenant_campuses",
        "ownership_types": ["public", "private"],
    },
}

_SKELETON_ARCHETYPES = frozenset({"state_emis_hub", "district_trust_overlay"})


def continent_key_for_row(row: dict[str, Any]) -> str:
    """Resolve continent defaults bucket — territories use the Territories bucket."""
    if row.get("territory") or is_likely_territory(str(row.get("iso_alpha2") or "")):
        return "Territories"
    continent = str(row.get("continent") or "Oceania")
    if continent not in CONTINENT_ARCHETYPE_DEFAULTS:
        return "Oceania"
    return continent


def apply_continent_defaults(alpha2: str, row: dict[str, Any]) -> None:
    """Fill governance defaults from continent archetype when row is still skeleton-level."""
    key = continent_key_for_row(row)
    defaults = CONTINENT_ARCHETYPE_DEFAULTS.get(key) or CONTINENT_ARCHETYPE_DEFAULTS["Oceania"]
    archetype = str(row.get("governance_archetype") or "")
    if archetype in _SKELETON_ARCHETYPES or archetype not in ARCHETYPES:
        row["governance_archetype"] = defaults["governance_archetype"]
    if str(row.get("employer_model") or "school") == "school" and key != "Territories":
        row["employer_model"] = defaults.get("employer_model", row.get("employer_model"))
    if row.get("reporting_chain") in (None, [], ["school"]):
        row["reporting_chain"] = list(defaults.get("reporting_chain") or ["school"])
    if not row.get("recommended_operating_mode"):
        row["recommended_operating_mode"] = defaults.get("recommended_operating_mode", "standalone")
    if not row.get("ownership_types"):
        row["ownership_types"] = list(defaults.get("ownership_types") or ["public", "private"])
    if not row.get("school_structure"):
        row["school_structure"] = defaults.get("school_structure", "both_common")
