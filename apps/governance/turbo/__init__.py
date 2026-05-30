"""Phase 6 turbocharge package.

Each submodule declares the contract for one of the 15 turbocharge deliverables.
The runtime implementations layer in over time; the contracts ship now so the
register has stable scaffolding and the verifiers have something to point at.
"""

TURBO_CONTRACTS: tuple[str, ...] = (
    "agentic_self_healing_matrix",
    "formal_verification_tla",
    "realtime_compliance_engine",
    "sovereignty_trust_score",
    "cross_vertical_kernel",
    "multimodal_terminology",
    "regulator_api_federation",
    "adversarial_redteam",
    "w3c_verifiable_credentials",
    "time_traveling_matrix",
    "zero_form_bootstrap",
    "ai_policy_copilot",
    "cross_org_marketplace",
    "federated_emis_aggregator",
    "living_competitor_tracker",
)
