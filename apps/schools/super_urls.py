from django.urls import path
from apps.marketplace import views as marketplace_views
from apps.customersuccess import views_super as cs_views
from . import super_views
from .control_plane import require_super_access
from .parent_tenant_views import parent_tenant_dashboard

app_name = "super"

urlpatterns = [
    path("", require_super_access(super_views.super_dashboard_v2), name="dashboard"),
    path("export/schools.csv", require_super_access(super_views.export_schools_csv), name="export_schools_csv"),
    path("export/revenue.csv", require_super_access(super_views.export_revenue_csv), name="export_revenue_csv"),
    path("command-center/", require_super_access(super_views.super_command_center_v2), name="command_center"),
    path("create/", require_super_access(super_views.create_school_wizard), name="create_school_wizard"),
    path("api/create-school/", require_super_access(super_views.api_create_school), name="api_create_school"),
    path("api/schools/<uuid:school_id>/timeline/", require_super_access(super_views.api_school_timeline), name="api_school_timeline"),
    path("api/schools/<uuid:school_id>/approve/", require_super_access(super_views.api_approve_school), name="api_approve_school"),
    path("api/geo/cities/", require_super_access(super_views.api_geo_cities), name="api_geo_cities"),
    path("api/geo/timezones/", require_super_access(super_views.api_geo_timezones), name="api_geo_timezones"),
    path("api/provinces/", require_super_access(super_views.api_provinces), name="api_provinces"),
    path("api/education-profiles/", require_super_access(super_views.api_education_profiles), name="api_education_profiles"),
    path("api/system-blueprint/", require_super_access(super_views.api_system_blueprint), name="api_system_blueprint"),
    path("api/plans-configurator/", require_super_access(super_views.api_plans_configurator), name="api_plans_configurator"),
    path("parent-tenant/", parent_tenant_dashboard, name="parent_tenant_dashboard"),
    path("usage/", require_super_access(super_views.super_usage), name="usage"),
    path("pulse/", require_super_access(super_views.super_pulse), name="pulse"),
    path("tenant-health/", require_super_access(super_views.super_tenant_health), name="tenant_health"),
    # Section 11: Benchmark intelligence (11.3) & Customer success (11.4)
    path("customer-success/", require_super_access(cs_views.customer_success_dashboard), name="customer_success_dashboard"),
    path("customer-success/api/benchmark/cohorts/", require_super_access(cs_views.api_benchmark_cohorts), name="cs_api_benchmark_cohorts"),
    path("customer-success/api/benchmark/peer-metrics/", require_super_access(cs_views.api_benchmark_peer_metrics), name="cs_api_benchmark_peer_metrics"),
    path("customer-success/api/maturity-scores/", require_super_access(cs_views.api_maturity_scores), name="cs_api_maturity_scores"),
    path("customer-success/api/risk-alerts/", require_super_access(cs_views.api_risk_alerts), name="cs_api_risk_alerts"),
    path("customer-success/api/intervention-suggestions/", require_super_access(cs_views.api_intervention_suggestions), name="cs_api_intervention_suggestions"),
    path("customer-success/api/tenant-health/", require_super_access(cs_views.api_tenant_health), name="cs_api_tenant_health"),
    path("customer-success/api/workflow-failures/", require_super_access(cs_views.api_workflow_failures), name="cs_api_workflow_failures"),
    path("customer-success/api/admin-inactivity-alerts/", require_super_access(cs_views.api_admin_inactivity_alerts), name="cs_api_admin_inactivity_alerts"),
    path("billing/", require_super_access(super_views.billing_dashboard), name="billing_dashboard"),
    path("marketplace/", marketplace_views.governance_console, name="marketplace_governance"),
    path("marketplace/reviews/<int:review_id>/action/", marketplace_views.marketplace_review_action, name="marketplace_review_action"),
    path("marketplace/blueprints/", marketplace_views.blueprint_marketplace, name="blueprint_marketplace"),
    path("marketplace/apps/", marketplace_views.app_catalog, name="app_catalog"),
    path("support/", require_super_access(super_views.super_support_dashboard), name="support_dashboard"),
    path("support/queue/", require_super_access(super_views.support_queue_fragment), name="support_queue_fragment"),
    path("switch-to-tenant/", require_super_access(super_views.switch_to_tenant), name="switch_to_tenant"),
    path("sync-repair/<uuid:school_id>/", require_super_access(super_views.sync_repair), name="sync_repair"),
    path("ai-model-hub/", require_super_access(super_views.ai_model_hub), name="ai_model_hub"),
    path("global-ai-version/", require_super_access(super_views.global_ai_version), name="global_ai_version"),
    path("global-ai-version/progress/<str:run_id>/", require_super_access(super_views.global_ai_version_progress), name="global_ai_version_progress"),
]
