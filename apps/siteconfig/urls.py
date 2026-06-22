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
    guided_onboarding_csv_apply,
    guided_onboarding_csv_dry_run,
    guided_onboarding_view,
    support_copilot_view,
    tenant_billing_estimate_view,
)
from .views_onboarding_coach import api_onboarding_coach
from .dashboard_views import (
    update_theme,
)
from .views_waiver import request_waiver
from .views_sidebar import sidebar_badge_counts, sidebar_settings_view
from .views_command_palette import command_palette_settings_view
from .views_custom_requirement import request_custom_requirement
from .views_sync_center import sync_center, sync_center_resolve
from .views_school_theme import school_theme_settings
from .views_theme_experience_hub import theme_experience_hub
from .views_theme_builder import (
    PaletteGenerateView,
    ThemeBuilderLayoutAPIView,
    ThemeBuilderPreviewAPIView,
    ThemeBuilderPublishAPIView,
    ThemeBuilderPublishLogAPIView,
    ThemeBuilderRollbackAPIView,
    theme_builder,
)
from .views_zero_ticket_hub import (
    campus_workflow_canvas_hub,
    api_brand_contrast_remediate,
    api_permission_matrix_export,
    api_permission_matrix_simulate,
    api_tenant_diagnostics,
    permission_matrix_simulator,
    zero_ticket_hub,
)
from apps.customersuccess.views_dashboard import tenant_health_dashboard
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
from .views_billing_stripe_connect import (
    billing_stripe_connect,
    billing_stripe_connect_return,
    billing_stripe_connect_start,
)
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
from apps.schools.views_group_console import group_console, group_console_upgrade
from .views_console_ai_rag import ingest_policy_docs as ai_rag_ingest_policy_docs
from .legacy_redirects import (
    legacy_customizer_clear_preview_redirect,
    legacy_customizer_redirect,
)
from .views_tenant_studio_hub import (
    TenantStudioDay1Act1LogoUploadView,
    TenantStudioDay1Act1View,
    TenantStudioDay1Act2View,
    TenantStudioDay1Act3LockView,
    TenantStudioDay1ResetView,
)
from .views_cockpit_admin import (
    CockpitConfigureView,
    CockpitShellConfigureView,
    MarketingVoiceConfigureView,
)
from .views_dashboard_defaults_admin import DashboardDefaultsAdminView
from .views_cockpit_previews import CockpitPreviewIndexView, CockpitPreviewServeView
from .views_cockpit_health import CockpitHealthView
from .views_theme_personality import ThemePersonalityConfigView

app_name = "siteconfig"

urlpatterns = [
    path("customizer/", legacy_customizer_redirect, name="legacy_customizer"),
    path(
        "customizer/clear-preview/",
        legacy_customizer_clear_preview_redirect,
        name="legacy_customizer_clear_preview",
    ),
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
        "schools/group-console/",
        group_console,
        name="group_console",
    ),
    path(
        "schools/group-console/upgrade/",
        group_console_upgrade,
        name="group_console_upgrade",
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
        "billing-stripe/",
        billing_stripe_connect,
        name="billing_stripe_connect",
    ),
    path(
        "billing-stripe/connect/",
        billing_stripe_connect_start,
        name="billing_stripe_connect_start",
    ),
    path(
        "billing-stripe/return/",
        billing_stripe_connect_return,
        name="billing_stripe_connect_return",
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
    path(
        "theme-experience/hub/",
        theme_experience_hub,
        name="theme_experience_hub",
    ),
    path(
        "theme-experience/builder/",
        theme_builder,
        name="theme_builder",
    ),
    path(
        "theme-experience/builder/api/layout/",
        ThemeBuilderLayoutAPIView.as_view(),
        name="theme_builder_layout_api",
    ),
    path(
        "theme-experience/builder/api/publish/",
        ThemeBuilderPublishAPIView.as_view(),
        name="theme_builder_publish_api",
    ),
    path(
        "theme-experience/builder/api/preview/",
        ThemeBuilderPreviewAPIView.as_view(),
        name="theme_builder_preview_api",
    ),
    path(
        "theme-experience/builder/api/publish-log/",
        ThemeBuilderPublishLogAPIView.as_view(),
        name="theme_builder_publish_log_api",
    ),
    path(
        "theme-experience/builder/api/rollback/",
        ThemeBuilderRollbackAPIView.as_view(),
        name="theme_builder_rollback_api",
    ),
    path(  # rbac-allow: tenant-or-staff-palette-generate
        "theme/palette/generate/",
        PaletteGenerateView.as_view(),
        name="palette_generate",
    ),
    path("zero-ticket/", zero_ticket_hub, name="zero_ticket_hub"),
    path(
        "zero-ticket/permissions/",
        permission_matrix_simulator,
        name="permission_matrix_simulator",
    ),
    path("zero-ticket/health/", tenant_health_dashboard, name="tenant_health_dashboard"),
    path(
        "zero-ticket/workflows/",
        campus_workflow_canvas_hub,
        name="campus_workflow_canvas_hub",
    ),
    path(
        "zero-ticket/api/diagnostics/",
        api_tenant_diagnostics,
        name="api_tenant_diagnostics",
    ),
    path(
        "zero-ticket/api/permissions/simulate/",
        api_permission_matrix_simulate,
        name="api_permission_matrix_simulate",
    ),
    path(
        "zero-ticket/api/permissions/export/",
        api_permission_matrix_export,
        name="api_permission_matrix_export",
    ),
    path(
        "zero-ticket/api/brand-contrast/remediate/",
        api_brand_contrast_remediate,
        name="api_brand_contrast_remediate",
    ),
    path("preview-from-form/", preview_from_form, name="preview_from_form"),
    path("preferences/", user_preferences, name="user_preferences"),
    path(
        "preferences/set-default-view/",
        set_default_dashboard_view,
        name="set_default_dashboard_view",
    ),
    path("preferences/theme/", update_theme, name="update_theme"),
    path("sidebar/badges/", sidebar_badge_counts, name="sidebar_badges"),
    path("sidebar/settings/", sidebar_settings_view, name="sidebar_settings"),
    path("command-palette/settings/", command_palette_settings_view, name="command_palette_settings"),
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
        "guided-onboarding/csv/dry-run/",
        guided_onboarding_csv_dry_run,
        name="guided_onboarding_csv_dry_run",
    ),
    path(
        "guided-onboarding/csv/apply/",
        guided_onboarding_csv_apply,
        name="guided_onboarding_csv_apply",
    ),
    path(
        "api/onboarding-coach/",
        api_onboarding_coach,
        name="api_onboarding_coach",
    ),
    path(
        "guided-onboarding/execute-launch/", execute_launch_view, name="execute_launch"
    ),
    path(
        "guided-onboarding/billing-estimate/",
        tenant_billing_estimate_view,
        name="tenant_billing_estimate",
    ),
    path("api/tour-steps/", tour_steps_api, name="tour_steps_api"),
    # rbac-allow: anonymous onboarding tour steps for marketing/login shells
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
    # Day-1 Magic — 3-act opening sequence for first /school/studio/ visit.
    path(
        "studio/day1/act1/",
        TenantStudioDay1Act1View.as_view(),
        name="tenant_studio_day1_act1",
    ),
    path(  # rbac-allow: tenant-admin-or-staff-day1-logo-upload
        "studio/day1/act1/logo-upload/",
        TenantStudioDay1Act1LogoUploadView.as_view(),
        name="tenant_studio_day1_act1_logo_upload",
    ),
    path(
        "studio/day1/act2/",
        TenantStudioDay1Act2View.as_view(),
        name="tenant_studio_day1_act2",
    ),
    path(
        "studio/day1/act3/lock/",
        TenantStudioDay1Act3LockView.as_view(),
        name="tenant_studio_day1_act3_lock",
    ),
    path(
        "studio/day1/reset/",
        TenantStudioDay1ResetView.as_view(),
        name="tenant_studio_day1_reset",
    ),
    # v3.56 cockpit configurability cascade — operator admin UI for the
    # 3 configurable cockpit blocks (footer, community_band, newsletter_band).
    # Realized URL on the control plane: /siteconfig/super/configure/cockpit/
    path(
        "super/configure/cockpit/",
        CockpitConfigureView.as_view(),
        name="cockpit_configure",
    ),
    # v8 cockpit shell chrome — skin per surface, header composition toggles,
    # emoji nav glyphs, page-header action buttons (cockpit_* brand_experience keys).
    # Realized URL on the control plane: /siteconfig/super/configure/cockpit/shell/
    path(
        "super/configure/cockpit/shell/",
        CockpitShellConfigureView.as_view(),
        name="cockpit_shell_configure",
    ),
    # Wave 15 (v3.62.20 — 2026-05-23): per-tenant marketing voice rich-edit.
    # Sister surface of cockpit_configure; targets only the marketing_voice
    # sub-tree of cockpit_payload via the dedicated MarketingVoiceForm with
    # live preview alongside.
    # Realized URL on the control plane: /siteconfig/super/configure/marketing-voice/
    # # rbac-allow: super-staff-marketing-voice-config
    path(
        "super/configure/marketing-voice/",
        MarketingVoiceConfigureView.as_view(),
        name="marketing_voice_configure",
    ),
    # v3.59.x Wave 11 Agent W (2026-05-22): operator-overridable theme
    # personality cockpit section. Reachable from both platform-operator
    # and tenant-operator consoles; the view's tenant-aware resolver writes
    # to the right SiteSettings row based on request.public_host_kind.
    # Realized URL on the control plane: /siteconfig/super/configure/theme-personality/
    # # rbac-allow: super-staff-theme-personality-config
    path(
        "super/configure/theme-personality/",
        ThemePersonalityConfigView.as_view(),
        name="theme_personality_configure",
    ),
    # v3.99.24 (2026-05-28): per-(role, page) dashboard defaults admin —
    # operator-curated requested_widget_ids + promoted_cockpit_ids that new
    # users inherit on first dashboard load.
    # # rbac-allow: super-staff-dashboard-defaults-admin
    path(
        "super/configure/dashboard-defaults/",
        DashboardDefaultsAdminView.as_view(),
        name="dashboard_defaults_admin",
    ),
    # v3.57.2 (2026-05-21): operator design-preview index + raw HTML serve
    # routes. Surfaces docs/generated/preview_app_shell_*.html behind staff
    # auth so operators can compare current shell behavior against published
    # design intent without filesystem access.
    path(
        "super/configure/cockpit/previews/",
        CockpitPreviewIndexView.as_view(),
        name="cockpit_previews",
    ),
    path(
        "super/configure/cockpit/previews/<slug:slug>/",
        CockpitPreviewServeView.as_view(),
        name="cockpit_preview_serve",
    ),
    # v3.57.7 (2026-05-22): cockpit health diagnostic — staff-only page
    # reporting live state of every cockpit section + demo-flag values + helper
    # module import status. Use this to debug why a section isn't rendering on
    # production without needing Render shell access.
    path(
        "super/configure/cockpit/health/",
        CockpitHealthView.as_view(),
        name="cockpit_health",
    ),
]
