"""
Governance runtime helpers (Phase 2B partial).

``governance_inherit`` lives in ``School.settings`` JSON — map of policy domains
to ``inherit`` | ``local`` | ``hybrid``. Documented domains align with the
global governance program: curriculum, fees, hr, branding, emis, integrations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.governance.operating_modes import (
    DEFAULT_GOVERNANCE_OPERATING_MODE,
    GovernanceOperatingMode,
)

if TYPE_CHECKING:
    from apps.schools.models import School

GOVERNANCE_INHERIT_SETTINGS_KEY = "governance_inherit"

KNOWN_INHERIT_DOMAINS: frozenset[str] = frozenset(
    {
        "curriculum",
        "fees",
        "hr",
        "branding",
        "emis",
        "integrations",
    }
)

InheritDisposition = str  # inherit | local | hybrid


def resolve_governance_operating_mode(school: "School | None") -> str:
    """
    Return the effective operating mode for ``school``.

    Standalone schools default to ``standalone``; nullable ``organization`` is
    not required for standalone operation.
    """
    if school is None:
        return GovernanceOperatingMode.STANDALONE
    mode = getattr(school, "governance_operating_mode", None) or ""
    mode = str(mode).strip()
    if mode in GovernanceOperatingMode.values:
        return mode
    return DEFAULT_GOVERNANCE_OPERATING_MODE


def _governance_inherit_map(school: "School | None") -> dict[str, Any]:
    if school is None:
        return {}
    settings_blob = getattr(school, "settings", None) or {}
    if not isinstance(settings_blob, dict):
        return {}
    raw = settings_blob.get(GOVERNANCE_INHERIT_SETTINGS_KEY)
    if not isinstance(raw, dict):
        return {}
    return raw


def inherit_domain(school: "School | None", domain: str) -> InheritDisposition:
    """
    Resolve inheritance disposition for a policy domain.

    - ``standalone`` schools always resolve to ``local``.
    - Unknown or missing domain entries default to ``local`` (fail-local).
    - Invalid disposition strings fall back to ``local``.
    """
    domain_key = (domain or "").strip().lower()
    if not domain_key:
        return "local"

    mode = resolve_governance_operating_mode(school)
    if mode == GovernanceOperatingMode.STANDALONE:
        return "local"

    inherit_map = _governance_inherit_map(school)
    raw = inherit_map.get(domain_key)
    if raw is None and domain_key not in KNOWN_INHERIT_DOMAINS:
        return "local"

    disposition = str(raw or "local").strip().lower()
    if disposition in {"inherit", "local", "hybrid"}:
        return disposition
    return "local"


def school_in_group_mode(school: "School | None") -> bool:
    """True when the school opted into organization group membership."""
    mode = resolve_governance_operating_mode(school)
    return mode in {
        GovernanceOperatingMode.GROUP_MEMBER,
        GovernanceOperatingMode.GROUP_MEMBER_SOVEREIGN,
    }
