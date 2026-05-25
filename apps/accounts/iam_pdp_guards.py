"""PDP advisory wiring for identity & access HTTP surfaces."""

from __future__ import annotations

from apps.policies.enforcement import pdp_advisory

# Collect PolicyDecisionLog rows before flipping POLICY_PDP_ENFORCEMENT_MODE=enforce.
rbac_dashboard_pdp = pdp_advisory(
    action="manage",
    resource_kind="access_role",
    rebac_permission="settings.manage",
)
tenant_identity_hub_pdp = pdp_advisory(
    action="manage",
    resource_kind="tenant_identity",
    rebac_permission="settings.manage",
)
tenant_regulator_grant_pdp = pdp_advisory(
    action="grant",
    resource_kind="regulatory_access",
    rebac_permission="settings.manage",
)
