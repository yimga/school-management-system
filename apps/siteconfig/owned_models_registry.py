"""
Siteconfig ownership migration (1.1): registry of model -> target bounded context.
Used by migration tooling and lint to enforce no new tenant behavior from SiteSettings.
See docs/SITECONFIG_OWNED_MODELS.md for full assignment.
"""
from __future__ import annotations

# Map: (app_label, model_name) -> target_app for migration
# Only siteconfig models that have a decided target are listed.
OWNED_MODELS_TARGET: dict[tuple[str, str], str] = {
    # siteconfig.models
    ("siteconfig", "SiteSettings"): "platform_runtime",
    ("siteconfig", "ThemePack"): "brand_experience",
    ("siteconfig", "Integration"): "platform_runtime",
    ("siteconfig", "UserPreference"): "platform_runtime",
    ("siteconfig", "FormDraft"): "platform_runtime",
    ("siteconfig", "ReportTemplate"): "reports",
    ("siteconfig", "OfficialReportTemplate"): "reports",
    ("siteconfig", "ReportCardStyle"): "reports",
    ("siteconfig", "RegionConfig"): "platform_runtime",
    ("siteconfig", "EducationSystemProfile"): "registries",
    ("siteconfig", "Province"): "registries",
    ("siteconfig", "TenantSystem"): "platform_runtime",
    ("siteconfig", "TenantAdmissionNumberPolicy"): "platform_runtime",
    ("siteconfig", "SystemFeature"): "plans",
    ("siteconfig", "Plan"): "plans",
    ("siteconfig", "SyncConflict"): "platform_runtime",
    ("siteconfig", "PlanAddon"): "plans",
    ("siteconfig", "CountryMultiplier"): "plans",
    ("siteconfig", "RegionalAIConfig"): "platform_runtime",
    ("siteconfig", "AIModelRegistry"): "platform_runtime",
    ("siteconfig", "AIEmbeddingStore"): "platform_runtime",
    ("siteconfig", "AIPromptRegistry"): "platform_runtime",
    ("siteconfig", "AIGatewayMetric"): "platform_runtime",
    ("siteconfig", "RevenueSnapshot"): "billing",
    ("siteconfig", "BillingWaiverAuditLog"): "billing",
    ("siteconfig", "WaiverRequest"): "billing",
    ("siteconfig", "CustomNuance"): "platform_runtime",
    ("siteconfig", "PendingNuance"): "platform_runtime",
    ("siteconfig", "ServiceIntegration"): "marketplace",
    ("siteconfig", "WebhookSubscription"): "apicenter",
    ("siteconfig", "WebhookDelivery"): "apicenter",
    ("siteconfig", "CustomFeatureTicket"): "platform_runtime",
    ("siteconfig", "FeatureFragment"): "platform_runtime",
    ("siteconfig", "DesignTemplate"): "brand_experience",
    ("siteconfig", "BrandProfile"): "brand_experience",
    ("siteconfig", "BrandSettings"): "brand_experience",
    ("siteconfig", "GradingScaleConfig"): "registries",
    ("siteconfig", "WeatherLocation"): "platform_runtime",
    ("siteconfig", "FeatureToggleDefinition"): "platform_runtime",
    ("siteconfig", "FeatureToggleState"): "platform_runtime",
    ("siteconfig", "TourStep"): "platform_runtime",
    ("siteconfig", "FeatureUsageEvent"): "platform_runtime",
    ("siteconfig", "GlobalSupportTicket"): "compliance",
    ("siteconfig", "RegionalPitch"): "schools",
    ("siteconfig", "GlobalBrandRegistry"): "brand_experience",
    ("siteconfig", "ImpersonationLog"): "accounts",
    ("siteconfig", "GlobalSyllabus"): "registries",
    ("siteconfig", "LearningPassport"): "people",
    ("siteconfig", "BreakGlassOverride"): "compliance",
    ("siteconfig", "BroadcastCampaign"): "communication",
    ("siteconfig", "ProductFeedback"): "platform_runtime",
    ("siteconfig", "MarketingContent"): "schools",
    ("siteconfig", "BlogPost"): "schools",
    ("siteconfig", "DynamicFieldDefinition"): "platform_runtime",
    ("siteconfig", "DynamicFieldValue"): "platform_runtime",
    # siteconfig.models_dashboard
    ("siteconfig", "DashboardUserPreference"): "platform_runtime",
    ("siteconfig", "SuperAdminDashboardPreference"): "platform_runtime",
    ("siteconfig", "DashboardWidget"): "platform_runtime",
    ("siteconfig", "WidgetData"): "platform_runtime",
    ("siteconfig", "DashboardLayout"): "platform_runtime",
    ("siteconfig", "DashboardLayoutAudit"): "platform_runtime",
    ("siteconfig", "FeatureControlAudit"): "platform_runtime",
    ("siteconfig", "DashboardPack"): "packages",
    ("siteconfig", "DashboardPackAssignment"): "packages",
    ("siteconfig", "DashboardTemplate"): "platform_runtime",
    ("siteconfig", "TenantLayoutAssignment"): "platform_runtime",
    # siteconfig.models_workflow
    ("siteconfig", "WorkflowPack"): "packages",
    ("siteconfig", "WorkflowPackAssignment"): "packages",
    ("siteconfig", "WorkflowTemplate"): "platform_runtime",
    ("siteconfig", "TenantWorkflow"): "platform_runtime",
    ("siteconfig", "WorkflowRunLog"): "orchestration",
}


def get_target_app_for_model(app_label: str, model_name: str) -> str | None:
    """Return target bounded-context app for a siteconfig model, or None if not yet assigned."""
    return OWNED_MODELS_TARGET.get((app_label, model_name))
