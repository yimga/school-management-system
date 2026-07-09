"""PDP ENFORCEMENT wiring for identity & access HTTP surfaces.

Promoted advisory → enforce 2026-07-09. Each guard carries a *parity probe* —
the surface's own canonical RBAC gate — whose verdict lands in the PDP subject
as ``subject.rbac_allowed``; the platform-baseline allow-rules seeded by
``policies`` migration 0010 condition on it, so enforcement starts at exact
access parity and tenant/operator deny rules (priority < 500) actually bind.

Placement contract: these guards sit INNERMOST on the view stack (below
``@login_required`` / ``@require_school`` / the coarse gates) so anonymous
users still get the login redirect and the PDP only sees requests the coarse
gates already admitted. Probes lazy-import their gate at request time to
avoid module-import cycles with the view modules that apply the guards.
"""

from __future__ import annotations

from apps.policies.enforcement import pdp_enforce


def _settings_manage_parity(request) -> bool:
    """Canonical tenant-config union: superuser / settings.manage code / admin tier."""
    from apps.accounts.effective_access import permission_access

    return permission_access(
        getattr(request, "user", None),
        getattr(request, "school", None),
        ("settings.manage",),
    )


def _identity_hub_parity(request) -> bool:
    """The identity hub's own gate (manage-tier membership roles + settings.manage)."""
    from apps.accounts.views_tenant_identity import _can_manage_tenant_identity

    return _can_manage_tenant_identity(
        getattr(request, "user", None), getattr(request, "school", None)
    )


rbac_dashboard_pdp = pdp_enforce(
    action="manage",
    resource_kind="access_role",
    rebac_permission="settings.manage",
    parity_probe=_settings_manage_parity,
)
tenant_identity_hub_pdp = pdp_enforce(
    action="manage",
    resource_kind="tenant_identity",
    rebac_permission="settings.manage",
    parity_probe=_identity_hub_parity,
)
tenant_regulator_grant_pdp = pdp_enforce(
    action="grant",
    resource_kind="regulatory_access",
    rebac_permission="settings.manage",
    parity_probe=_identity_hub_parity,
)
