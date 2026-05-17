from django.urls import path

from .views import (
    region_grading_scales_view,
    region_validation_dashboard,
    region_comparison_view,
    branding_api,
    workflow_clues_api,
    admission_number_preview_api,
    maintenance_view,
    grading_settings,
    module_market,
    clear_preview,
    preview_from_form,
    download_report,
    bulk_letters,
    scheduled_reports_delivery_hub,
    reportcard_builder,
    reportcard_style_preview,
    reportcard_style_embed_preview,
    reportcard_style_live_preview,
    reportcard_style_pdf,
    user_preferences,
    set_default_dashboard_view,
    theme_colors_page,
    theme_experience_redirect,
    brand_import_from_url_view,
    template_gallery_page,
    toggle_preview_mode,
    set_act_as_role,
)
from .views_feature_control import (
    feature_control_panel,
    feature_control_export,
    feature_control_audit_log,
    feature_control_api,
    feature_control_weather_cities,
    feature_control_ledger,
)
from .views_dashboard_config import (
    dashboard_configuration_hub,
    dashboard_hub,
    workflow_flow_gallery,
    get_blueprints,
)
from .views_workflow_api import (
    workflow_catalog_api,
    workflow_list_api,
    workflow_run_api,
    workflow_preview_api,
    dashboard_registry_api,
)
from .views_school_automation import (
    school_automation_builder,
    school_automation_execution_logs_api,
    school_automation_list_api,
    school_automation_publish_api,
    school_automation_retry_api,
    school_automation_run_api,
    school_automation_save_api,
    school_automation_simulate_api,
)
from apps.marketplace.views import sandbox_embed as marketplace_sandbox_embed
from apps.customersuccess.views_tenant import (
    execute_launch_view,
    guided_onboarding_view,
    support_copilot_view,
)
from .views_onboarding_coach import api_onboarding_coach
from .dashboard_views import (
    update_theme,
)
from .views_waiver import request_waiver
from .views_custom_requirement import request_custom_requirement
from .views_sync_center import sync_center, sync_center_resolve
from .views_school_theme import school_theme_settings
from .views_tag_manager import tag_manager, tag_manager_edit
from .views_impersonation_consent import (
    grant_impersonation_consent,
    revoke_impersonation_consent,
)
from .views_form_draft import form_draft_api
from .views import feedback_roadmap
from .views_package_rollback import tenant_installed_packages_rollback
from .views_console_domains import console_domains_hub
from .views_entity_catalog import entity_catalog_overview
from .views_metadata_operator_hub import metadata_operator_hub
from .views_metadata_dynamic_fields import metadata_dynamic_fields_operator
from .views_config_mutation_evidence import config_mutation_audit_evidence
from .views_term_publish_evidence import term_publish_status_evidence
from .views_academic_years_evidence import academic_years_setup_evidence
from .views_departments_setup_evidence import departments_setup_evidence
from .views_tenant_runtime_hub import tenant_runtime_configuration_hub
from .views_guided_configuration import guided_configuration_workflows
from .views_grading_scale_bands import grading_scale_bands_operator_view
from .views_curriculum_templates import curriculum_templates_operator_view
from .views_compliance_exports import (
    compliance_export_download_view,
    compliance_exports_view,
)
from .views_northstar_ai import northstar_ai_draft_api
from .views_ai_governance import ai_governance
from .views_ai_center import ai_center
from .views_billing_plan import billing_plan_readonly
from .views_billing_stripe import billing_checkout_start, billing_customer_portal
from .views_tour import tour_steps_api, tour_steps_public_api
from .views_tour_analytics import tour_analytics_api
from .views_tour_info import tour_info_tag_api
from .views_report_output_history_evidence import report_output_history_evidence
from .views_report_templates_catalog_evidence import report_templates_catalog_evidence
from .views_tenant_report_schedules_evidence import tenant_report_schedules_evidence
from apps.schools.views_domains import custom_domain_wizard
from .views_school_onboarding import (
    onboarding_step_detail,
    onboarding_step_mark_complete,
    school_activation_onboarding,
)
from .views_school_group_hierarchy import school_group_hierarchy
from .views_console_ai_rag import ingest_policy_docs as ai_rag_ingest_policy_docs

app_name = "siteconfig"

urlpatterns = [
    path("maintenance/", maintenance_view, name="maintenance"),
    path(
        "dev/mascot/",
        __import__("apps.siteconfig.views_mascot_storybook", fromlist=["mascot_storybook"]).mascot_storybook,
        name="mascot_storybook",
    ),
    path(
        "onboarding/step/complete/",
        onboarding_step_mark_complete,
        name="onboarding_step_complete",
    ),
    path(
        "onboarding/step/<str:step_key>/",
        onboarding_step_detail,
        name="onboarding_step",
    ),
    path("onboarding/", school_activation_onboarding, name="onboarding"),
    path("console/", console_domains_hub, name="console_domains_hub"),
    path(
        "metadata/operator-hub/",
        metadata_operator_hub,
        name="metadata_operator_hub",
    ),
    path(
        "metadata/entity-catalog/",
        entity_catalog_overview,
        name="entity_catalog_overview",
    ),
    path(
        "metadata/dynamic-fields/",
        metadata_dynamic_fields_operator,
        name="metadata_dynamic_fields_operator",
    ),
    path(
        "metadata/config-mutation-audit/",
        config_mutation_audit_evidence,
        name="config_mutation_audit_evidence",
    ),
    path(
        "configuration/runtime/",
        tenant_runtime_configuration_hub,
        name="tenant_runtime_configuration_hub",
    ),
    path(
        "configuration/guided/",
        guided_configuration_workflows,
        name="guided_configuration_workflows",
    ),
    path(
        "schools/group-hierarchy/",
        school_group_hierarchy,
        name="school_group_hierarchy",
    ),
    path(
        "billing/plan/",
        billing_plan_readonly,
        name="billing_plan_readonly",
    ),
    path(
        "billing/checkout/start/",
        billing_checkout_start,
        name="billing_checkout_start",
    ),
    path(
        "billing/portal/",
        billing_customer_portal,
        name="billing_customer_portal",
    ),
    path(
        "ai/governance/",
        ai_governance,
        name="ai_governance",
    ),
    path(
        "ai-center/",
        ai_center,
        name="ai_center",
    ),
    path("grading-settings/", grading_settings, name="grading_settings"),
    path(
        "grading-scales/bands/",
        grading_scale_bands_operator_view,
        name="grading_scale_bands",
    ),
    path(
        "curriculum/templates/",
        curriculum_templates_operator_view,
        name="curriculum_templates",
    ),
    path(
        "compliance/exports/",
        compliance_exports_view,
        name="compliance_exports",
    ),
    path(
        "compliance/exports/<slug:export_key>/download/",
        compliance_export_download_view,
        name="compliance_export_download",
    ),
    path(
        "grading-scales/region-scales/",
        region_grading_scales_view,
        name="region_grading_scales",
    ),
    path(
        "regions/validation/",
        region_validation_dashboard,
        name="region_validation",
    ),
    path(
        "regions/comparison/",
        region_comparison_view,
        name="region_comparison",
    ),
    path("modules/", module_market, name="module_market"),
    path(
        "installed-packages/",
        tenant_installed_packages_rollback,
        name="installed_packages_rollback",
    ),
    path("preview/clear/", clear_preview, name="clear_preview"),
    path("theme-colors/", theme_colors_page, name="theme_colors"),
    path(
        "theme-colors/import-from-url/",
        brand_import_from_url_view,
        name="brand_import_from_url",
    ),
    path("template-gallery/", template_gallery_page, name="template_gallery"),
    path(
        "theme-experience/", theme_experience_redirect, name="theme_experience_redirect"
    ),
    path("preview-from-form/", preview_from_form, name="preview_from_form"),
    path("preferences/", user_preferences, name="user_preferences"),
    path(
        "preferences/set-default-view/",
        set_default_dashboard_view,
        name="set_default_dashboard_view",
    ),
    path("preferences/theme/", update_theme, name="update_theme"),
    path("reports/download/<slug:slug>/", download_report, name="report_download"),
    path("reports/bulk-letters/", bulk_letters, name="bulk_letters"),
    path(
        "reports/northstar-ai/draft/",
        northstar_ai_draft_api,
        name="northstar_ai_draft",
    ),
    path(
        "reports/scheduled/",
        scheduled_reports_delivery_hub,
        name="scheduled_reports_delivery_hub",
    ),
    path(
        "reports/tenant-schedules-evidence/",
        tenant_report_schedules_evidence,
        name="tenant_report_schedules_evidence",
    ),
    path(
        "reports/report-templates-catalog/",
        report_templates_catalog_evidence,
        name="report_templates_catalog_evidence",
    ),
    path(
        "reports/output-history-evidence/",
        report_output_history_evidence,
        name="report_output_history_evidence",
    ),
    path(
        "reports/term-publish-status/",
        term_publish_status_evidence,
        name="term_publish_status_evidence",
    ),
    path(
        "reports/academic-years-setup/",
        academic_years_setup_evidence,
        name="academic_years_setup_evidence",
    ),
    path(
        "reports/departments-setup/",
        departments_setup_evidence,
        name="departments_setup_evidence",
    ),
    path("reports/builder/", reportcard_builder, name="reportcard_builder"),
    path(
        "reports/preview/<slug:slug>/",
        reportcard_style_preview,
        name="reportcard_style_preview",
    ),
    path(
        "reports/embed-preview/<slug:slug>/<str:report_type>/",
        reportcard_style_embed_preview,
        name="reportcard_style_embed_preview",
    ),
    path(
        "reports/live-preview/<slug:slug>/<str:report_type>/",
        reportcard_style_live_preview,
        name="reportcard_style_live_preview",
    ),
    path(
        "reports/preview/<slug:slug>/<str:report_type>/pdf/",
        reportcard_style_pdf,
        name="reportcard_style_pdf",
    ),
    path("preview/toggle/", toggle_preview_mode, name="toggle_preview_mode"),
    path("act-as/", set_act_as_role, name="set_act_as_role"),
    path("feature-control/", feature_control_panel, name="feature_control_panel"),
    path(
        "feature-control/export/", feature_control_export, name="feature_control_export"
    ),
    path(
        "feature-control/audit/",
        feature_control_audit_log,
        name="feature_control_audit",
    ),
    path(
        "feature-control/ledger/", feature_control_ledger, name="feature_control_ledger"
    ),
    path("feature-control/api/", feature_control_api, name="feature_control_api"),
    path(
        "feature-control/weather-cities/",
        feature_control_weather_cities,
        name="feature_control_weather_cities",
    ),
    path("dashboard-hub/", dashboard_hub, name="dashboard_hub"),
    path(
        "dashboard-configuration/",
        dashboard_configuration_hub,
        name="dashboard_configuration_hub",
    ),
    path("workflow-gallery/", workflow_flow_gallery, name="workflow_flow_gallery"),
    path("get-blueprints/", get_blueprints, name="get_blueprints"),
    path("request-waiver/", request_waiver, name="request_waiver"),
    path(
        "request-custom-requirement/",
        request_custom_requirement,
        name="request_custom_requirement",
    ),
    path("sync-center/", sync_center, name="sync_center"),
    path(
        "sync-center/resolve/<int:conflict_id>/",
        sync_center_resolve,
        name="sync_center_resolve",
    ),
    path("school-theme/", school_theme_settings, name="school_theme_settings"),
    path("tag-manager/", tag_manager, name="tag_manager"),
    path("tag-manager/<int:tag_id>/", tag_manager_edit, name="tag_manager_edit"),
    path("domains/", custom_domain_wizard, name="custom_domain_wizard"),
    path("api/branding/", branding_api, name="branding_api"),
    path("api/workflow-clues/", workflow_clues_api, name="workflow_clues_api"),
    path(
        "api/admission-number-preview/",
        admission_number_preview_api,
        name="admission_number_preview_api",
    ),
    path("api/workflow/catalog/", workflow_catalog_api, name="workflow_catalog_api"),
    path("api/workflow/list/", workflow_list_api, name="workflow_list_api"),
    path("api/workflow/run/", workflow_run_api, name="workflow_run_api"),
    path("api/workflow/preview/", workflow_preview_api, name="workflow_preview_api"),
    path(
        "automation/builder/",
        school_automation_builder,
        name="school_automation_builder",
    ),
    path(
        "api/school-automation/list/",
        school_automation_list_api,
        name="school_automation_list_api",
    ),
    path(
        "api/school-automation/save/",
        school_automation_save_api,
        name="school_automation_save_api",
    ),
    path(
        "api/school-automation/publish/",
        school_automation_publish_api,
        name="school_automation_publish_api",
    ),
    path(
        "api/school-automation/simulate/",
        school_automation_simulate_api,
        name="school_automation_simulate_api",
    ),
    path(
        "api/school-automation/run/",
        school_automation_run_api,
        name="school_automation_run_api",
    ),
    path(
        "api/school-automation/execution-logs/",
        school_automation_execution_logs_api,
        name="school_automation_execution_logs_api",
    ),
    path(
        "api/school-automation/retry/",
        school_automation_retry_api,
        name="school_automation_retry_api",
    ),
    path(
        "api/dashboard-registry/", dashboard_registry_api, name="dashboard_registry_api"
    ),
    path("api/form-draft/<str:form_key>/", form_draft_api, name="form_draft_api"),
    path("app-sandbox/", marketplace_sandbox_embed, name="marketplace_sandbox_embed"),
    path("support-copilot/", support_copilot_view, name="support_copilot"),
    path("guided-onboarding/", guided_onboarding_view, name="guided_onboarding"),
    path(
        "api/onboarding-coach/",
        api_onboarding_coach,
        name="api_onboarding_coach",
    ),
    path(
        "guided-onboarding/execute-launch/", execute_launch_view, name="execute_launch"
    ),
    path("api/tour-steps/", tour_steps_api, name="tour_steps_api"),
    path("api/tour-steps/public/", tour_steps_public_api, name="tour_steps_public_api"),
    path("api/tour-analytics/", tour_analytics_api, name="tour_analytics_api"),
    path("api/tour-info/", tour_info_tag_api, name="tour_info_tag_api"),
    path(
        "impersonation-consent/grant/",
        grant_impersonation_consent,
        name="grant_impersonation_consent",
    ),
    path(
        "impersonation-consent/revoke/",
        revoke_impersonation_consent,
        name="revoke_impersonation_consent",
    ),
    path("feedback-roadmap/", feedback_roadmap, name="feedback_roadmap"),
    path(
        "console/ai/rag/ingest/",
        ai_rag_ingest_policy_docs,
        name="ai_rag_ingest_policy_docs",
    ),
]
