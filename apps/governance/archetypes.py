"""
Governance archetype catalog — four global patterns (+ hybrids at signup/runtime).

Archetypes suggest org structure templates; every school may remain standalone.
Country matrix rows reference these keys via ``governance_archetype``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GovernanceArchetype:
    key: str
    label: str
    description: str
    typical_legal_owner_types: tuple[str, ...]
    default_operating_mode: str


ARCHETYPE_SINGLE_ORG_MULTI_SITE = GovernanceArchetype(
    key="single_org_multi_site",
    label="Single organization, multiple sites",
    description=(
        "One legal owner operates multiple school tenants (international groups, "
        "proprietor chains, single-entity multi-campus networks)."
    ),
    typical_legal_owner_types=("corporation", "proprietor", "franchise"),
    default_operating_mode="group_member",
)

ARCHETYPE_DISTRICT_TRUST_OVERLAY = GovernanceArchetype(
    key="district_trust_overlay",
    label="District / trust overlay",
    description=(
        "Overlay governance body (LEA, MAT, diocese, territory education office) "
        "coordinates member schools while each tenant keeps isolation."
    ),
    typical_legal_owner_types=("diocese", "ministry", "corporation"),
    default_operating_mode="group_member",
)

ARCHETYPE_FEDERATION_EQUALS = GovernanceArchetype(
    key="federation_equals",
    label="Federation of equals",
    description=(
        "Peer schools or campuses under a loose federation (NGO clusters, proprietor "
        "networks, cooperative trusts) with configurable per-domain inheritance."
    ),
    typical_legal_owner_types=("ngo", "proprietor", "corporation"),
    default_operating_mode="group_member_sovereign",
)

ARCHETYPE_STATE_EMIS_HUB = GovernanceArchetype(
    key="state_emis_hub",
    label="State EMIS hub",
    description=(
        "Ministry-led reporting hub: schools remain tenants; statutory exports and "
        "admin labels route through state/regional EMIS expectations."
    ),
    typical_legal_owner_types=("ministry",),
    default_operating_mode="group_member",
)

GOVERNANCE_ARCHETYPES: Mapping[str, GovernanceArchetype] = {
    ARCHETYPE_SINGLE_ORG_MULTI_SITE.key: ARCHETYPE_SINGLE_ORG_MULTI_SITE,
    ARCHETYPE_DISTRICT_TRUST_OVERLAY.key: ARCHETYPE_DISTRICT_TRUST_OVERLAY,
    ARCHETYPE_FEDERATION_EQUALS.key: ARCHETYPE_FEDERATION_EQUALS,
    ARCHETYPE_STATE_EMIS_HUB.key: ARCHETYPE_STATE_EMIS_HUB,
}

ALLOWED_ARCHETYPE_KEYS: frozenset[str] = frozenset(GOVERNANCE_ARCHETYPES.keys())


def get_archetype(key: str) -> GovernanceArchetype | None:
    return GOVERNANCE_ARCHETYPES.get((key or "").strip())
