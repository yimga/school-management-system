"""
Registry of resolver entry points (plan Workstream C2 / Codex §4).
Single source of truth for runtime resolution; used by build_tenant_runtime and observability.
"""
from __future__ import annotations

# Resolver names and their implementation location (for docs and admin inspection).
RESOLVER_ENTRY_POINTS = [
    ("RuntimeResolver", "apps.platform_runtime.runtime_resolver.build_tenant_runtime"),
    ("SchemaResolver", "apps.metadata.services (entity/field catalog)"),
    ("LayoutResolver", "apps.siteconfig (layouts, forms, role homes)"),
    ("BrandingResolver", "apps.platform_runtime.runtime_resolver._step7_branding"),
    ("BlueprintResolver", "apps.platform_runtime.runtime_resolver._step4_blueprint"),
    ("PolicyResolver", "apps.policies.resolver.get_effective_policy"),
    ("WorkflowResolver", "apps.siteconfig.workflow_resolver.for_action"),
    ("DashboardResolver", "apps.siteconfig.dashboard_resolver.for_role"),
    ("EntitlementResolver", "apps.platform_runtime.runtime_resolver._step6_flags"),
    ("IntegrationResolver", "apps.platform_runtime.runtime_resolver._step10_integrations"),
    ("LocalizationResolver", "apps.platform_runtime.runtime_resolver._step3_registry"),
]
