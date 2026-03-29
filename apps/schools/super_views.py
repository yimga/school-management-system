"""
Super Admin views: re-exports from BR-12 split modules (dashboard, APIs, wizard, etc.).
Access restricted to SUPERADMIN or is_superuser via TenantSuperAdminRequiredMiddleware.
"""

from .super_views_geo_api import (
    api_education_profiles,
    api_geo_cities,
    api_geo_timezones,
    api_plans_configurator,
    api_provinces,
    api_system_blueprint,
)
from .super_views_school_api import (
    api_approve_school,
    api_school_policy_bundle_activate,
    api_school_policy_bundles,
    api_school_timeline,
    school_lifecycle_action,
)
from .super_views_phase_b import super_phase_b_snapshot_diff
from .super_views_policy import (
    super_apply_policy_bundle_to_sandbox,
    super_policy_diff,
)
from .super_views_trust_surface import (
    super_audit_export,
    super_compliance_overview,
    super_config_hub_redirect,
    super_platform_events,
    super_trust_center,
)
from .super_views_support import (
    super_support_csat_dashboard,
    super_support_dashboard,
    super_support_ticket_detail,
    super_support_tickets_export_csv,
    support_assign_ticket,
    support_queue_fragment,
)
from .super_views_ai import (
    ai_model_hub,
    global_ai_version,
    global_ai_version_progress,
    super_ai_gateway_console,
)
from .super_views_impersonation import switch_to_tenant
from .super_views_runtime_ops import (
    super_playbook_operator_hub,
    super_runtime_inspector,
    super_runtime_truth_hub,
    super_workflow_simulator,
)
from .super_views_platform_monitoring import (
    super_control_health_dashboard,
    super_pulse,
    super_tenant_360,
    super_tenant_health,
    super_usage,
)
from .super_views_billing_console import billing_dashboard
from .super_views_command_center_views import (
    super_command_center,
    super_command_center_v2,
)
from .super_views_overview_surfaces import (
    super_analytics_overview,
    super_schools_list,
)

from .super_views_dashboard_surfaces import (
    api_super_dashboard_layout,
    super_dashboard,
    super_dashboard_v2,
)
from .super_views_exports import (
    export_revenue_csv,
    export_schools_csv,
    export_super_dashboard_pdf,
)
from .super_views_create_school_wizard import create_school_wizard


# Re-exported callables for `super_urls` (`import super_views` + attribute access).
# Listed in ``__all__`` so Ruff F401 does not flag intentional namespace exports.
__all__ = (
    "ai_model_hub",
    "super_ai_gateway_console",
    "api_approve_school",
    "api_super_dashboard_layout",
    "billing_dashboard",
    "api_education_profiles",
    "api_geo_cities",
    "api_geo_timezones",
    "api_plans_configurator",
    "api_provinces",
    "api_school_policy_bundle_activate",
    "api_school_policy_bundles",
    "api_school_timeline",
    "api_system_blueprint",
    "create_school_wizard",
    "export_revenue_csv",
    "export_schools_csv",
    "export_super_dashboard_pdf",
    "global_ai_version",
    "global_ai_version_progress",
    "school_lifecycle_action",
    "super_dashboard",
    "super_dashboard_v2",
    "super_analytics_overview",
    "super_schools_list",
    "super_playbook_operator_hub",
    "super_runtime_inspector",
    "super_runtime_truth_hub",
    "super_workflow_simulator",
    "switch_to_tenant",
    "super_phase_b_snapshot_diff",
    "super_apply_policy_bundle_to_sandbox",
    "super_control_health_dashboard",
    "super_audit_export",
    "super_compliance_overview",
    "super_command_center",
    "super_command_center_v2",
    "super_config_hub_redirect",
    "super_platform_events",
    "super_policy_diff",
    "super_pulse",
    "super_support_dashboard",
    "super_support_csat_dashboard",
    "super_support_ticket_detail",
    "super_support_tickets_export_csv",
    "super_tenant_360",
    "super_tenant_health",
    "super_trust_center",
    "super_usage",
    "support_assign_ticket",
    "support_queue_fragment",
)

# Re-export migration/sync-repair views for super_urls (decomposed from this file)
