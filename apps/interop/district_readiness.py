"""District / LEA readiness payloads (fixtures + future HTTP ingress).

Normalizes Ed-Fi- and CEDS-shaped JSON into a small canonical dict so adapters
and API tests can share one contract (SOT §11.4 batch 13 #130).
"""

from __future__ import annotations

from typing import Any


def parse_district_readiness_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Parse a district-readiness envelope into canonical keys.

    Raises:
        ValueError: unknown ``envelope`` or ``sourceSystem``.
    """
    env = data.get("envelope")
    if env != "district-readiness-v1":
        raise ValueError(f"unsupported envelope: {env!r}")
    src = data.get("sourceSystem")
    if src == "edfi":
        did = data.get("districtIdentifier")
        name = data.get("nameOfInstitution")
        if not did or not name:
            raise ValueError("edfi payload missing districtIdentifier or nameOfInstitution")
        return {
            "envelope": env,
            "source_system": "edfi",
            "district_identifier": str(did),
            "name": str(name),
            "state_organization_id": data.get("stateOrganizationId"),
        }
    if src == "ceds":
        did = data.get("leaIdentifier")
        name = data.get("leaName")
        if not did or not name:
            raise ValueError("ceds payload missing leaIdentifier or leaName")
        return {
            "envelope": env,
            "source_system": "ceds",
            "district_identifier": str(did),
            "name": str(name),
            "state_abbreviation": data.get("stateAbbreviation"),
        }
    raise ValueError(f"unsupported sourceSystem: {src!r}")
