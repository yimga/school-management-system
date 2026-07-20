# -*- coding: utf-8 -*-
"""
Platform admin changelist bridges: slug → Django admin URL name + hub copy.

Covers **every** model on ``platform_admin_site`` (see merge from
``platform_admin_surface_bridges``): siteconfig, integrations_marketplace,
marketplace native, runtime_blueprints, global_registries, packages,
brand_experience, platform_runtime, automation, billing, observability,
policies, registries, schools, etc. Operators use ``super:admin_bridge`` instead
of hardcoded ``/admin/...`` paths.

Used by ``super_admin_bridge`` (302) and ``super_platform_operator_hub`` tiles.
Nav must use ``reverse("super:admin_bridge", kwargs={"bridge_key": "<slug>"})``.
Legacy **paths** (e.g. ``…/integrations-marketplace/``) remain in ``super_urls`` and
**301** to the canonical slug URL, then 302 to platform admin.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from .platform_admin_surface_bridges import (
    PLATFORM_ADMIN_SURFACE_BRIDGE_ORDER,
    PLATFORM_ADMIN_SURFACE_BRIDGES,
)

# Display order on the platform operator hub (admin-tagged tiles).
PLATFORM_ADMIN_BRIDGE_ORDER: list[str] = [
    # Original high-traffic bridges (also in control plane nav)
    "integrations",
    "service_integrations",
    "marketplace_apps",
    "packages_installed",
    "experience_packs",
    "runtime_defaults",
    "phase_b_domain_snapshots",
    "fleet_governed_changes",
    "ai_model_registry",
    "global_brand_registry",
    "platform_global_branding",
    # Packages — remainder
    "document_packs",
    "package_versions",
    "package_changelog",
    # Siteconfig / AI / revenue / sync
    "regional_ai_config",
    "ai_prompt_registry",
    "ai_gateway_metrics",
    "revenue_snapshots",
    "waiver_requests",
    "sync_conflicts",
    # Blueprints / registries / ops
    "super_dashboard_preferences",
    "education_system_profiles",
    "provinces",
    # Duplicative of super list views — hub-only shortcuts to raw admin
    "migration_runs_admin",
    "platform_incidents_admin",
    # --- Full platform-admin coverage (siteconfig remainder, global_registries, runtime_blueprints, integrations_marketplace) ---
    "ai_embedding_store",
    "billing_waiver_audit_log",
    "stripe_plan_prices",
    "billing_entitlements",
    "custom_nuance",
    "pending_nuance",
    "custom_feature_ticket",
    "feature_fragment",
    "feature_control_audit",
    "break_glass_override",
    "broadcast_campaign",
    "product_feedback",
    "marketing_content",
    "blog_post",
    "system_features",
    "tenant_systems",
    "blueprint_packs",
    "blueprint_compatibility_rules",
    "tenant_blueprints",
    "form_drafts",
    "app_audit_logs",
    "app_billing_ledgers",
    "app_installations",
    "app_scopes",
    "app_version_compat",
    "capability_registry",
    "marketplace_listings",
    "marketplace_reviews",
    "publisher_organizations",
    "scope_grants",
    # siteconfig register_both (also on platform admin)
    "report_templates",
    "official_report_templates",
    "report_card_styles",
    "feature_toggle_states",
    "tour_steps",
    "feature_usage_events",
    "workflow_run_logs",
    "global_syllabi",
    "learning_passports",
    # runtime_blueprints register_both (platform + tenant)
    "dashboard_layouts",
    "dashboard_packs",
    "dashboard_pack_assignments",
    "dashboard_templates",
    "dashboard_widgets",
    "workflow_packs",
    "workflow_pack_assignments",
    "workflow_templates",
    # apps.sales — platform_admin_site (internal pipeline)
    "sales_leads",
    "sales_pipeline_stages",
    # apps.apicenter — OAuth / developer platform admin
    "apicenter_developer_application",
    "apicenter_marketplace_extension_submission",
    "apicenter_oauth_authorization_code",
    "apicenter_oauth_token_pair",
    # compliance + native marketplace catalog (platform admin)
    "compliance_audit_log",
    "app_permission_scopes",
    "platform_event_logs",
    "event_webhook_subscriptions",
    "event_webhook_deliveries",
    "studio_experience_region_approvals",
]

# bridge_key (URL slug) → config
PLATFORM_ADMIN_BRIDGES: dict[str, dict[str, object]] = {
    "integrations": {
        "admin_url": "admin:integrations_marketplace_integration_changelist",
        "label": _("Integrations (platform admin)"),
        "description": _(
            "Integration rows — use after reviewing One SIS / any LMS"
        ),
        "icon": "bi-diagram-3",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_integrations",
        "nav_label": _("Integrations registry (admin)"),
        "nav_icon": "bi-diagram-3",
    },
    "service_integrations": {
        "admin_url": "admin:integrations_marketplace_serviceintegration_changelist",
        "label": _("Service integrations (platform admin)"),
        "description": _("ServiceIntegration — connected services beside Integration catalog"),
        "icon": "bi-plugin",
        "show_in_nav": False,
    },
    "marketplace_apps": {
        "admin_url": "admin:integrations_marketplace_marketplaceapp_changelist",
        "label": _("Marketplace apps (platform admin)"),
        "description": _(
            "Publisher MarketplaceApp maintenance — complements governance & install flows"
        ),
        "icon": "bi-grid",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_marketplace_apps",
        "nav_label": _("Marketplace apps (admin)"),
        "nav_icon": "bi-grid",
    },
    "packages_installed": {
        "admin_url": "admin:packages_installedpackage_changelist",
        "label": _("Installed packages (platform admin)"),
        "description": _("Tenant package installs — audit beside Package rollout"),
        "icon": "bi-box-seam-fill",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_packages_installed",
        "nav_label": _("Installed packages (admin)"),
        "nav_icon": "bi-box-seam-fill",
    },
    "experience_packs": {
        "admin_url": "admin:packages_experiencepack_changelist",
        "label": _("Experience packs (platform admin)"),
        "description": _("ExperiencePack definitions — pairs with rollout & catalog"),
        "icon": "bi-collection",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_experience_packs",
        "nav_label": _("Experience packs (admin)"),
        "nav_icon": "bi-collection",
    },
    "runtime_defaults": {
        "admin_url": "admin:platform_runtime_runtimedefaults_changelist",
        "label": _("Runtime defaults (platform admin)"),
        "description": _(
            "platform_runtime.RuntimeDefaults — resolver baselines, preview flags, "
            "and non-secret integration defaults (SMS/WhatsApp identity fields; secrets stay in JSON)"
        ),
        "icon": "bi-speedometer2",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_runtime_defaults",
        "nav_label": _("Runtime defaults (admin)"),
        "nav_icon": "bi-speedometer2",
    },
    "phase_b_domain_snapshots": {
        "admin_url": "admin:platform_runtime_platformphasebdomainsnapshot_changelist",
        "label": _("Phase B domain snapshots (platform admin)"),
        "description": _(
            "platform_runtime.PlatformPhaseBDomainSnapshot — owned JSON per domain "
            "(policies, marketplace_integrations, metadata_governance, …). Use the control-plane "
            "“Phase B snapshot diff” page to compare live owned_payload fingerprints to stored rows."
        ),
        "icon": "bi-diagram-2",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_phase_b_domain_snapshots",
        "nav_label": _("Phase B domain snapshots (admin)"),
        "nav_icon": "bi-diagram-2",
    },
    "fleet_governed_changes": {
        "admin_url": "admin:platform_runtime_fleetgovernedchange_changelist",
        "label": _("Fleet governed changes (platform admin)"),
        "description": _(
            "Draft → approval → schedule → apply records; execution uses existing rollout/staging UIs"
        ),
        "icon": "bi-clipboard-check",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_fleet_governed_changes",
        "nav_label": _("Fleet governed changes (admin)"),
        "nav_icon": "bi-clipboard-check",
    },
    "ai_model_registry": {
        "admin_url": "admin:siteconfig_aimodelregistry_changelist",
        "label": _("AI model registry (platform admin)"),
        "description": _("siteconfig.AIModelRegistry rows — raw admin beside AI model hub"),
        "icon": "bi-gpu-card",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_ai_model_registry",
        "nav_label": _("AI model registry (admin)"),
        "nav_icon": "bi-gpu-card",
    },
    "global_brand_registry": {
        "admin_url": "admin:brand_experience_globalbrandregistry_changelist",
        "label": _("Global brand registry (platform admin)"),
        "description": _("brand_experience.GlobalBrandRegistry — fleet branding catalog"),
        "icon": "bi-palette-fill",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_global_brand_registry",
        "nav_label": _("Global brand registry (admin)"),
        "nav_icon": "bi-palette-fill",
    },
    "platform_global_branding": {
        "admin_url": "admin:brand_experience_platformglobalbranding_changelist",
        "label": _("Platform global branding (platform admin)"),
        "description": _(
            "brand_experience.PlatformGlobalBranding — active fleet branding defaults"
        ),
        "icon": "bi-palette",
        "show_in_nav": True,
        "nav_id": "cp_admin_bridge_platform_global_branding",
        "nav_label": _("Platform global branding (admin)"),
        "nav_icon": "bi-palette",
    },
    # --- Hub-first (large set; avoid sidebar overflow) ---
    "document_packs": {
        "admin_url": "admin:packages_documentpack_changelist",
        "label": _("Document packs (platform admin)"),
        "description": _("DocumentPack definitions — pairs with package rollout"),
        "icon": "bi-file-earmark-richtext",
        "show_in_nav": False,
    },
    "package_versions": {
        "admin_url": "admin:packages_packageversion_changelist",
        "label": _("Package versions (platform admin)"),
        "description": _("PackageVersion rows — version lineage"),
        "icon": "bi-layers",
        "show_in_nav": False,
    },
    "package_changelog": {
        "admin_url": "admin:packages_packagechangelog_changelist",
        "label": _("Package changelog (platform admin)"),
        "description": _("PackageChangeLog — release history"),
        "icon": "bi-journal-text",
        "show_in_nav": False,
    },
    "regional_ai_config": {
        "admin_url": "admin:siteconfig_regionalaiconfig_changelist",
        "label": _("Regional AI config (platform admin)"),
        "description": _("RegionalAIConfig — locale/model routing"),
        "icon": "bi-globe2",
        "show_in_nav": False,
    },
    "ai_prompt_registry": {
        "admin_url": "admin:siteconfig_aipromptregistry_changelist",
        "label": _("AI prompt registry (platform admin)"),
        "description": _("AIPromptRegistry — prompts beside gateway"),
        "icon": "bi-chat-square-text",
        "show_in_nav": False,
    },
    "ai_gateway_metrics": {
        "admin_url": "admin:siteconfig_aigatewaymetric_changelist",
        "label": _("AI gateway metrics (platform admin)"),
        "description": _("AIGatewayMetric — usage & latency samples"),
        "icon": "bi-graph-up-arrow",
        "show_in_nav": False,
    },
    "revenue_snapshots": {
        "admin_url": "admin:siteconfig_revenuesnapshot_changelist",
        "label": _("Revenue snapshots (platform admin)"),
        "description": _("RevenueSnapshot — MRR / waived aggregates"),
        "icon": "bi-cash-stack",
        "show_in_nav": False,
    },
    "waiver_requests": {
        "admin_url": "admin:siteconfig_waiverrequest_changelist",
        "label": _("Waiver requests (platform admin)"),
        "description": _("WaiverRequest — billing exceptions queue"),
        "icon": "bi-patch-check",
        "show_in_nav": False,
    },
    "sync_conflicts": {
        "admin_url": "admin:siteconfig_syncconflict_changelist",
        "label": _("Sync conflicts (platform admin)"),
        "description": _("SyncConflict — Studio sync reconciliation"),
        "icon": "bi-arrow-left-right",
        "show_in_nav": False,
    },
    "super_dashboard_preferences": {
        "admin_url": "admin:runtime_blueprints_superadmindashboardpreference_changelist",
        "label": _("Super dashboard preferences (platform admin)"),
        "description": _("SuperAdminDashboardPreference — section order storage"),
        "icon": "bi-layout-text-window-reverse",
        "show_in_nav": False,
    },
    "education_system_profiles": {
        "admin_url": "admin:global_registries_educationsystemprofile_changelist",
        "label": _("Education system profiles (platform admin)"),
        "description": _("EducationSystemProfile — global catalog maintenance"),
        "icon": "bi-mortarboard",
        "show_in_nav": False,
    },
    "provinces": {
        "admin_url": "admin:global_registries_province_changelist",
        "label": _("Provinces (platform admin)"),
        "description": _("Province — geo subdivisions"),
        "icon": "bi-geo",
        "show_in_nav": False,
    },
    "migration_runs_admin": {
        "admin_url": "admin:automation_migrationrun_changelist",
        "label": _("Migration runs (platform admin)"),
        "description": _("Raw MigrationRun changelist — beside super migration list"),
        "icon": "bi-hdd-network",
        "show_in_nav": False,
    },
    "platform_incidents_admin": {
        "admin_url": "admin:observability_platformincident_changelist",
        "label": _("Incidents (platform admin)"),
        "description": _("Raw PlatformIncident changelist — beside super incidents"),
        "icon": "bi-bug",
        "show_in_nav": False,
    },
    # siteconfig — remaining register_platform_admin models
    "ai_embedding_store": {
        "admin_url": "admin:siteconfig_aiembeddingstore_changelist",
        "label": _("AI embedding store (platform admin)"),
        "description": _("AIEmbeddingStore — vector storage audit"),
        "icon": "bi-database",
        "show_in_nav": False,
    },
    "billing_waiver_audit_log": {
        "admin_url": "admin:siteconfig_billingwaiverauditlog_changelist",
        "label": _("Billing waiver audit log (platform admin)"),
        "description": _("BillingWaiverAuditLog — waiver audit trail"),
        "icon": "bi-clipboard-data",
        "show_in_nav": False,
    },
    "stripe_plan_prices": {
        "admin_url": "admin:billing_stripeplanprice_changelist",
        "label": _("Stripe plan prices (platform admin)"),
        "description": _("StripePlanPrice — commercial plan/price rows"),
        "icon": "bi-currency-dollar",
        "show_in_nav": False,
    },
    "billing_entitlements": {
        "admin_url": "admin:billing_entitlement_changelist",
        "label": _("Billing entitlements (platform admin)"),
        "description": _("Entitlement — materialized tenant feature and quota grants"),
        "icon": "bi-shield-check",
        "show_in_nav": False,
    },
    "custom_nuance": {
        "admin_url": "admin:siteconfig_customnuance_changelist",
        "label": _("Custom nuance (platform admin)"),
        "description": _("CustomNuance — tenant nuance requests"),
        "icon": "bi-sliders",
        "show_in_nav": False,
    },
    "pending_nuance": {
        "admin_url": "admin:siteconfig_pendingnuance_changelist",
        "label": _("Pending nuance (platform admin)"),
        "description": _("PendingNuance — nuance queue"),
        "icon": "bi-hourglass-split",
        "show_in_nav": False,
    },
    "custom_feature_ticket": {
        "admin_url": "admin:siteconfig_customfeatureticket_changelist",
        "label": _("Custom feature tickets (platform admin)"),
        "description": _("CustomFeatureTicket — bespoke feature requests"),
        "icon": "bi-clipboard-check",
        "show_in_nav": False,
    },
    "feature_fragment": {
        "admin_url": "admin:siteconfig_featurefragment_changelist",
        "label": _("Feature fragments (platform admin)"),
        "description": _("FeatureFragment — partial feature payloads"),
        "icon": "bi-puzzle",
        "show_in_nav": False,
    },
    "feature_control_audit": {
        "admin_url": "admin:siteconfig_featurecontrolaudit_changelist",
        "label": _("Feature control audit (platform admin)"),
        "description": _("FeatureControlAudit — toggle/flag audit"),
        "icon": "bi-shield-check",
        "show_in_nav": False,
    },
    "break_glass_override": {
        "admin_url": "admin:siteconfig_breakglassoverride_changelist",
        "label": _("Break-glass overrides (platform admin)"),
        "description": _("BreakGlassOverride — emergency access"),
        "icon": "bi-unlock",
        "show_in_nav": False,
    },
    "broadcast_campaign": {
        "admin_url": "admin:siteconfig_broadcastcampaign_changelist",
        "label": _("Broadcast campaigns (platform admin)"),
        "description": _("BroadcastCampaign — fleet messaging"),
        "icon": "bi-megaphone",
        "show_in_nav": False,
    },
    "product_feedback": {
        "admin_url": "admin:siteconfig_productfeedback_changelist",
        "label": _("Product feedback (platform admin)"),
        "description": _("ProductFeedback — inbound product signals"),
        "icon": "bi-chat-dots",
        "show_in_nav": False,
    },
    "marketing_content": {
        "admin_url": "admin:siteconfig_marketingcontent_changelist",
        "label": _("Marketing content (platform admin)"),
        "description": _("MarketingContent — CMS-style blocks"),
        "icon": "bi-newspaper",
        "show_in_nav": False,
    },
    "blog_post": {
        "admin_url": "admin:siteconfig_blogpost_changelist",
        "label": _("Blog posts (platform admin)"),
        "description": _("BlogPost — marketing blog"),
        "icon": "bi-journal-richtext",
        "show_in_nav": False,
    },
    # global_registries — platform proxy tables
    "system_features": {
        "admin_url": "admin:global_registries_systemfeature_changelist",
        "label": _("System features (platform admin)"),
        "description": _("SystemFeature — capability flags"),
        "icon": "bi-stars",
        "show_in_nav": False,
    },
    "tenant_systems": {
        "admin_url": "admin:global_registries_tenantsystem_changelist",
        "label": _("Tenant systems (platform admin)"),
        "description": _("TenantSystem — tenant↔system links"),
        "icon": "bi-diagram-2",
        "show_in_nav": False,
    },
    # runtime_blueprints — platform-only catalogs
    "blueprint_packs": {
        "admin_url": "admin:runtime_blueprints_blueprintpack_changelist",
        "label": _("Blueprint packs (platform admin)"),
        "description": _("BlueprintPack — blueprint definitions"),
        "icon": "bi-boxes",
        "show_in_nav": False,
    },
    "blueprint_compatibility_rules": {
        "admin_url": "admin:runtime_blueprints_blueprintcompatibilityrule_changelist",
        "label": _("Blueprint compatibility rules (platform admin)"),
        "description": _("BlueprintCompatibilityRule — compatibility matrix"),
        "icon": "bi-intersect",
        "show_in_nav": False,
    },
    "tenant_blueprints": {
        "admin_url": "admin:runtime_blueprints_tenantblueprint_changelist",
        "label": _("Tenant blueprints (platform admin)"),
        "description": _("TenantBlueprint — tenant bindings"),
        "icon": "bi-link-45deg",
        "show_in_nav": False,
    },
    "form_drafts": {
        "admin_url": "admin:runtime_blueprints_formdraft_changelist",
        "label": _("Form drafts (platform admin)"),
        "description": _("FormDraft — Studio form drafts"),
        "icon": "bi-file-earmark-text",
        "show_in_nav": False,
    },
    # integrations_marketplace — platform proxy tables (beyond Integration / MarketplaceApp)
    "app_audit_logs": {
        "admin_url": "admin:integrations_marketplace_appauditlog_changelist",
        "label": _("App audit logs (platform admin)"),
        "description": _("AppAuditLog — install/scope audit"),
        "icon": "bi-list-check",
        "show_in_nav": False,
    },
    "app_billing_ledgers": {
        "admin_url": "admin:integrations_marketplace_appbillingledger_changelist",
        "label": _("App billing ledgers (platform admin)"),
        "description": _("AppBillingLedger — marketplace billing"),
        "icon": "bi-currency-dollar",
        "show_in_nav": False,
    },
    "app_installations": {
        "admin_url": "admin:integrations_marketplace_appinstallation_changelist",
        "label": _("App installations (platform admin)"),
        "description": _("AppInstallation — install rows"),
        "icon": "bi-download",
        "show_in_nav": False,
    },
    "app_scopes": {
        "admin_url": "admin:integrations_marketplace_appscope_changelist",
        "label": _("App scopes (platform admin)"),
        "description": _("AppScope — capability scopes"),
        "icon": "bi-bounding-box",
        "show_in_nav": False,
    },
    "app_version_compat": {
        "admin_url": "admin:integrations_marketplace_appversioncompat_changelist",
        "label": _("App version compatibility (platform admin)"),
        "description": _("AppVersionCompat — version matrix"),
        "icon": "bi-check2-square",
        "show_in_nav": False,
    },
    "capability_registry": {
        "admin_url": "admin:integrations_marketplace_capabilityregistry_changelist",
        "label": _("Capability registry (platform admin)"),
        "description": _("CapabilityRegistry — global capability catalog"),
        "icon": "bi-grid-3x3",
        "show_in_nav": False,
    },
    "marketplace_listings": {
        "admin_url": "admin:integrations_marketplace_marketplacelisting_changelist",
        "label": _("Marketplace listings (platform admin)"),
        "description": _("MarketplaceListing — listing rows"),
        "icon": "bi-shop",
        "show_in_nav": False,
    },
    "marketplace_reviews": {
        "admin_url": "admin:integrations_marketplace_marketplacereview_changelist",
        "label": _("Marketplace reviews (platform admin)"),
        "description": _("MarketplaceReview — reviews"),
        "icon": "bi-star",
        "show_in_nav": False,
    },
    "publisher_organizations": {
        "admin_url": "admin:integrations_marketplace_publisherorganization_changelist",
        "label": _("Publisher organizations (platform admin)"),
        "description": _("PublisherOrganization — publishers"),
        "icon": "bi-building",
        "show_in_nav": False,
    },
    "scope_grants": {
        "admin_url": "admin:integrations_marketplace_scopegrant_changelist",
        "label": _("Scope grants (platform admin)"),
        "description": _("ScopeGrant — granted scopes"),
        "icon": "bi-key",
        "show_in_nav": False,
    },
    # siteconfig — register_both (platform backoffice shares these changelists)
    "report_templates": {
        "admin_url": "admin:siteconfig_reporttemplate_changelist",
        "label": _("Report templates (platform admin)"),
        "description": _("ReportTemplate — report definitions"),
        "icon": "bi-file-earmark-bar-graph",
        "show_in_nav": False,
    },
    "official_report_templates": {
        "admin_url": "admin:siteconfig_officialreporttemplate_changelist",
        "label": _("Official report templates (platform admin)"),
        "description": _("OfficialReportTemplate — official templates"),
        "icon": "bi-file-earmark-check",
        "show_in_nav": False,
    },
    "report_card_styles": {
        "admin_url": "admin:siteconfig_reportcardstyle_changelist",
        "label": _("Report card styles (platform admin)"),
        "description": _("ReportCardStyle — transcript styling"),
        "icon": "bi-palette",
        "show_in_nav": False,
    },
    "feature_toggle_states": {
        "admin_url": "admin:siteconfig_featuretogglestate_changelist",
        "label": _("Feature toggle states (platform admin)"),
        "description": _("FeatureToggleState — per-tenant toggle values"),
        "icon": "bi-toggle-on",
        "show_in_nav": False,
    },
    "tour_steps": {
        "admin_url": "admin:siteconfig_tourstep_changelist",
        "label": _("Tour steps (platform admin)"),
        "description": _("TourStep — guided tour content"),
        "icon": "bi-signpost",
        "show_in_nav": False,
    },
    "feature_usage_events": {
        "admin_url": "admin:siteconfig_featureusageevent_changelist",
        "label": _("Feature usage events (platform admin)"),
        "description": _("FeatureUsageEvent — usage telemetry"),
        "icon": "bi-graph-up",
        "show_in_nav": False,
    },
    "workflow_run_logs": {
        "admin_url": "admin:siteconfig_workflowrunlog_changelist",
        "label": _("Workflow run logs (platform admin)"),
        "description": _("WorkflowRunLog — workflow execution audit"),
        "icon": "bi-clock-history",
        "show_in_nav": False,
    },
    "global_syllabi": {
        "admin_url": "admin:siteconfig_globalsyllabus_changelist",
        "label": _("Global syllabi (platform admin)"),
        "description": _("GlobalSyllabus — shared syllabus catalog"),
        "icon": "bi-book",
        "show_in_nav": False,
    },
    "learning_passports": {
        "admin_url": "admin:siteconfig_learningpassport_changelist",
        "label": _("Learning passports (platform admin)"),
        "description": _("LearningPassport — learner credentials"),
        "icon": "bi-award",
        "show_in_nav": False,
    },
    # runtime_blueprints — register_both
    "dashboard_layouts": {
        "admin_url": "admin:runtime_blueprints_dashboardlayout_changelist",
        "label": _("Dashboard layouts (platform admin)"),
        "description": _("DashboardLayout — layout definitions"),
        "icon": "bi-layout-three-columns",
        "show_in_nav": False,
    },
    "dashboard_packs": {
        "admin_url": "admin:runtime_blueprints_dashboardpack_changelist",
        "label": _("Dashboard packs (platform admin)"),
        "description": _("DashboardPack — dashboard pack catalog"),
        "icon": "bi-grid-1x2",
        "show_in_nav": False,
    },
    "dashboard_pack_assignments": {
        "admin_url": "admin:runtime_blueprints_dashboardpackassignment_changelist",
        "label": _("Dashboard pack assignments (platform admin)"),
        "description": _("DashboardPackAssignment — tenant bindings"),
        "icon": "bi-link",
        "show_in_nav": False,
    },
    "dashboard_templates": {
        "admin_url": "admin:runtime_blueprints_dashboardtemplate_changelist",
        "label": _("Dashboard templates (platform admin)"),
        "description": _("DashboardTemplate — widget templates"),
        "icon": "bi-window",
        "show_in_nav": False,
    },
    "dashboard_widgets": {
        "admin_url": "admin:runtime_blueprints_dashboardwidget_changelist",
        "label": _("Dashboard widgets (platform admin)"),
        "description": _("DashboardWidget — widget definitions"),
        "icon": "bi-app",
        "show_in_nav": False,
    },
    "workflow_packs": {
        "admin_url": "admin:runtime_blueprints_workflowpack_changelist",
        "label": _("Workflow packs (platform admin)"),
        "description": _("WorkflowPack — workflow pack catalog"),
        "icon": "bi-diagram-3",
        "show_in_nav": False,
    },
    "workflow_pack_assignments": {
        "admin_url": "admin:runtime_blueprints_workflowpackassignment_changelist",
        "label": _("Workflow pack assignments (platform admin)"),
        "description": _("WorkflowPackAssignment — tenant workflow bindings"),
        "icon": "bi-node-plus",
        "show_in_nav": False,
    },
    "workflow_templates": {
        "admin_url": "admin:runtime_blueprints_workflowtemplate_changelist",
        "label": _("Workflow templates (platform admin)"),
        "description": _("WorkflowTemplate — workflow graph templates"),
        "icon": "bi-share",
        "show_in_nav": False,
    },
    "sales_leads": {
        "admin_url": "admin:sales_lead_changelist",
        "label": _("Sales leads (platform admin)"),
        "description": _("Lead — platform pipeline (internal)"),
        "icon": "bi-person-lines-fill",
        "show_in_nav": False,
    },
    "sales_pipeline_stages": {
        "admin_url": "admin:sales_pipelinestage_changelist",
        "label": _("Pipeline stages (platform admin)"),
        "description": _("PipelineStage — internal stage catalog"),
        "icon": "bi-funnel",
        "show_in_nav": False,
    },
    "apicenter_developer_application": {
        "admin_url": "admin:apicenter_developerapplication_changelist",
        "label": _("Developer applications (platform admin)"),
        "description": _("OAuth/developer registrations on the API Center"),
        "icon": "bi-app-indicator",
        "show_in_nav": False,
    },
    "apicenter_marketplace_extension_submission": {
        "admin_url": "admin:apicenter_marketplaceextensionsubmission_changelist",
        "label": _("Marketplace extension submissions (platform admin)"),
        "description": _("Publisher extension submissions for API Center review"),
        "icon": "bi-box-arrow-in-down",
        "show_in_nav": False,
    },
    "apicenter_oauth_authorization_code": {
        "admin_url": "admin:apicenter_oauthauthorizationcode_changelist",
        "label": _("OAuth authorization codes (platform admin)"),
        "description": _("Authorization codes issued by the developer OAuth flow"),
        "icon": "bi-key",
        "show_in_nav": False,
    },
    "apicenter_oauth_token_pair": {
        "admin_url": "admin:apicenter_oauthtokenpair_changelist",
        "label": _("OAuth token pairs (platform admin)"),
        "description": _("Access/refresh token pairs for API Center OAuth clients"),
        "icon": "bi-shield-lock",
        "show_in_nav": False,
    },
    "compliance_audit_log": {
        "admin_url": "admin:compliance_auditlog_changelist",
        "label": _("Compliance audit log (platform admin)"),
        "description": _("AuditLog — enterprise audit trail rows"),
        "icon": "bi-journal-text",
        "show_in_nav": False,
    },
    "app_permission_scopes": {
        "admin_url": "admin:marketplace_apppermissionscope_changelist",
        "label": _("App permission scopes (platform admin)"),
        "description": _("AppPermissionScope — OAuth/catalog permission strings"),
        "icon": "bi-key-fill",
        "show_in_nav": False,
    },
}

PLATFORM_ADMIN_BRIDGES.update(
    {
        "platform_event_logs": {
            "admin_url": "admin:platform_runtime_platformeventlog_changelist",
            "label": _("Platform event logs (platform admin)"),
            "description": _("PlatformEventLog rows for event integrity and replay audit"),
            "icon": "bi-activity",
            "show_in_nav": False,
        },
        "event_webhook_subscriptions": {
            "admin_url": "admin:platform_runtime_eventwebhooksubscription_changelist",
            "label": _("Event webhook subscriptions (platform admin)"),
            "description": _("Tenant webhook subscriptions for event backbone delivery"),
            "icon": "bi-broadcast-pin",
            "show_in_nav": False,
        },
        "event_webhook_deliveries": {
            "admin_url": "admin:platform_runtime_eventwebhookdelivery_changelist",
            "label": _("Event webhook deliveries (platform admin)"),
            "description": _("Webhook delivery attempts, outcomes, and retry evidence"),
            "icon": "bi-send-check",
            "show_in_nav": False,
        },
        "studio_experience_region_approvals": {
            "admin_url": "admin:studio_os_experienceregionapproval_changelist",
            "label": _("Studio experience region approvals (platform admin)"),
            "description": _(
                "Read-only cross-tenant proof-before-publish approval trail"
            ),
            "icon": "bi-patch-check",
            "show_in_nav": False,
        },
    }
)

_overlap = set(PLATFORM_ADMIN_BRIDGE_ORDER) & set(PLATFORM_ADMIN_SURFACE_BRIDGE_ORDER)
if _overlap:
    raise RuntimeError(
        f"Duplicate bridge keys between base and surface: {_overlap}"
    )
_overlap_b = set(PLATFORM_ADMIN_BRIDGES.keys()) & set(PLATFORM_ADMIN_SURFACE_BRIDGES.keys())
if _overlap_b:
    raise RuntimeError(
        f"Duplicate bridge keys in dict merge: {_overlap_b}"
    )

PLATFORM_ADMIN_BRIDGE_ORDER.extend(PLATFORM_ADMIN_SURFACE_BRIDGE_ORDER)
PLATFORM_ADMIN_BRIDGES.update(PLATFORM_ADMIN_SURFACE_BRIDGES)
