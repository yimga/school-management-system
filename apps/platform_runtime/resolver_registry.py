"""
Registry of resolver entry points (plan Workstream C2 / Codex §4).
Single source of truth for runtime resolution; used by build_tenant_runtime and observability.

When adding a new runtime facet (NEXT_50 step 21):
  1. Implement the resolver (e.g. in platform_runtime.runtime_resolver or the owning app).
  2. Append a (name, location) tuple to RESOLVER_ENTRY_POINTS below — name is the resolver
     label (e.g. "NewResolver"); location is a dotted Python path or "app.module (description)".
  3. Run apps.platform_runtime.tests.test_runtime_contract.ResolverRegistryContractTests
     so the new entry is covered (dotted paths must be importable).
  4. Document any cross-context contract in docs/bounded_context_ownership.md if the
     resolver crosses bounded contexts.
"""

from __future__ import annotations

# Resolver names and their implementation location (for docs and admin inspection).
RESOLVER_ENTRY_POINTS = [
    ("RuntimeResolver", "apps.platform_runtime.runtime_resolver.build_tenant_runtime"),
    ("SchemaResolver", "apps.metadata (entity/field catalog; schema in .services)"),
    ("LayoutResolver", "apps.siteconfig (layouts, forms, role homes)"),
    ("BrandingResolver", "apps.platform_runtime.runtime_resolver._step7_branding"),
    ("BlueprintResolver", "apps.platform_runtime.runtime_resolver._step4_blueprint"),
    ("PolicyResolver", "apps.policies.resolver.get_effective_policy"),
    ("WorkflowResolver", "apps.siteconfig.workflow_resolver.for_action"),
    ("DashboardResolver", "apps.siteconfig.dashboard_resolver.for_role"),
    (
        "EntitlementResolver",
        "apps.platform_runtime.runtime_resolver._step6_flags_entitlements",
    ),
    (
        "EntitlementRegistrySnapshot",
        "apps.platform_runtime.registry_snapshots.build_entitlement_registry_snapshot",
    ),
    (
        "IntegrationResolver",
        "apps.platform_runtime.runtime_resolver._step10_integrations_marketplace",
    ),
    (
        "LocalizationResolver",
        "apps.platform_runtime.runtime_resolver._step3_registry_context",
    ),
]
