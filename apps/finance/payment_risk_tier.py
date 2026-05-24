"""
Payment corridor risk tiers (SFDP Phase 3 — batch 1458).

low / medium / high / counsel_blocked — drives allowed operator actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_COUNSEL_BLOCKED = "counsel_blocked"

ALLOWED_RISK_TIERS: frozenset[str] = frozenset(
    {RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_COUNSEL_BLOCKED}
)

COUNSEL_BLOCKED_ISO2: frozenset[str] = frozenset()  # extend when counsel docket flags a corridor

HIGH_RISK_ISO2: frozenset[str] = frozenset({"NG", "GH", "CM", "KE", "ZA", "IN", "BR", "MX"})


@dataclass(frozen=True)
class RiskDecision:
    tier: str
    reason: str
    allow_live_charge: bool
    allow_split_payout: bool
    allow_connect_onboarding: bool


def default_risk_tier_for_country(iso2: str | None) -> str:
    code = str(iso2 or "").strip().upper()[:2]
    if not code:
        return RISK_MEDIUM
    if code in COUNSEL_BLOCKED_ISO2:
        return RISK_COUNSEL_BLOCKED
    if code in HIGH_RISK_ISO2:
        return RISK_HIGH
    return RISK_MEDIUM


def evaluate_risk(profile: dict[str, Any] | None) -> RiskDecision:
    if not profile:
        return RiskDecision(
            tier=RISK_MEDIUM,
            reason="no_regional_profile",
            allow_live_charge=True,
            allow_split_payout=False,
            allow_connect_onboarding=True,
        )
    tier = str(profile.get("risk_tier") or default_risk_tier_for_country(profile.get("country_code")))
    if tier not in ALLOWED_RISK_TIERS:
        tier = RISK_MEDIUM
    reason = str(profile.get("risk_reason") or f"profile_risk_{tier}")
    counsel = tier == RISK_COUNSEL_BLOCKED
    return RiskDecision(
        tier=tier,
        reason=reason,
        allow_live_charge=not counsel,
        allow_split_payout=tier == RISK_LOW and not counsel,
        allow_connect_onboarding=not counsel,
    )
