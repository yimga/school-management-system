# Siteconfig Owned Models — Target Bounded Context (1.1)

**Purpose:** Assign every model currently under `siteconfig` to a target bounded context for Phase 10 migration. Used by 1.2 (state-safe migrations) and 1.3 (delete legacy).

**Rule:** Target app = canonical owner after migration. Until migrations run, code may still live in siteconfig; this doc is the source of truth for *where* each model will move.

---

## apps/siteconfig/models.py

| Model | Target bounded context | Target app | Notes |
|-------|------------------------|------------|--------|
| SiteSettings | Runtime defaults / tenant config | platform_runtime | Replace with runtime resolvers + Defaults/tenant config tables |
| ThemePack | Theme / experience | brand_experience | Theme + layout; ExperiencePack (10.1) may supersede |
| Integration | Runtime / marketplace | platform_runtime or marketplace | Provider config, API keys |
| UserPreference | Runtime / accounts | platform_runtime or accounts | User-level preferences |
| FormDraft | Runtime / portal | platform_runtime or portal | Form draft state |
| ReportTemplate | Reports | reports | Report library (10.3 ReportPack later) |
| OfficialReportTemplate | Reports | reports | |
| ReportCardStyle | Reports / brand | reports or brand_experience | |
| RegionConfig | Runtime / plans | platform_runtime or plans | Region, geo, rate limits |
| EducationSystemProfile | Runtime / registries | registries | Education profile engine |
| Province | Registries / geo | registries | |
| TenantSystem | Runtime | platform_runtime | Tenant/school system flags |
| TenantAdmissionNumberPolicy | Runtime / people | platform_runtime or people | |
| SystemFeature | Plans / entitlements | plans | Feature flags tied to plan |
| Plan | Plans | plans | Plan, entitlements |
| SyncConflict | Runtime | platform_runtime | Sync/conflict resolution |
| PlanAddon | Plans | plans | |
| CountryMultiplier | Plans / billing | plans or billing | |
| RegionalAIConfig | Runtime / AI | platform_runtime | AI config per region |
| AIModelRegistry | Runtime / AI | platform_runtime | |
| AIEmbeddingStore | Runtime / AI | platform_runtime | |
| AIPromptRegistry | Runtime / AI | platform_runtime | |
| AIGatewayMetric | Runtime / AI | platform_runtime | |
| RevenueSnapshot | Billing | billing | |
| BillingWaiverAuditLog | Billing | billing | |
| WaiverRequest | Billing | billing | |
| CustomNuance | Runtime / i18n | platform_runtime | |
| PendingNuance | Runtime / i18n | platform_runtime | |
| ServiceIntegration | Runtime / marketplace | marketplace or platform_runtime | |
| WebhookSubscription | Developer platform / API | apicenter or api | 8.1 developer platform |
| WebhookDelivery | Developer platform / API | apicenter or api | |
| CustomFeatureTicket | Plans / feature control | plans or platform_runtime | |
| FeatureFragment | Runtime / feature control | platform_runtime | |
| DesignTemplate | Brand / experience | brand_experience | |
| BrandProfile | Brand | brand_experience | |
| BrandSettings | Brand | brand_experience | |
| GradingScaleConfig | Academics / registries | registries or academics | |
| WeatherLocation | Runtime / observability | platform_runtime or observability | |
| FeatureToggleDefinition | Runtime / feature control | platform_runtime | 10.2 Feature Control |
| FeatureToggleState | Runtime / feature control | platform_runtime | |
| TourStep | Runtime / UX | platform_runtime | Product tours |
| FeatureUsageEvent | Runtime / feature control | platform_runtime | |
| GlobalSupportTicket | Compliance / support | compliance or customersuccess | |
| RegionalPitch | Marketing | (marketing or schools) | |
| GlobalBrandRegistry | Brand / registries | brand_experience or registries | |
| ImpersonationLog | Security / accounts | accounts or compliance | |
| GlobalSyllabus | Registries / academics | registries | |
| LearningPassport | People / academics | people or academics | |
| BreakGlassOverride | Security / compliance | compliance or platform_runtime | |
| BroadcastCampaign | Communication | communication | |
| ProductFeedback | Runtime / support | platform_runtime or customersuccess | |
| MarketingContent | Marketing | (marketing surface) | 7.1 marketing AI |
| BlogPost | Marketing | (marketing surface) | |
| DynamicFieldDefinition | Runtime / metadata | platform_runtime or metadata | |
| DynamicFieldValue | Runtime / metadata | platform_runtime or metadata | |

---

## apps/siteconfig/models_dashboard.py

| Model | Target bounded context | Target app | Notes |
|-------|------------------------|------------|--------|
| DashboardUserPreference | Runtime / dashboard | platform_runtime | |
| SuperAdminDashboardPreference | Runtime / super | platform_runtime or schools | |
| DashboardWidget | Runtime / dashboard | platform_runtime | |
| WidgetData | Runtime / dashboard | platform_runtime | |
| DashboardLayout | Runtime / dashboard | platform_runtime | |
| DashboardLayoutAudit | Runtime / dashboard | platform_runtime | |
| FeatureControlAudit | Runtime / feature control | platform_runtime | 10.2 |
| DashboardPack | Runtime / packages | packages | Dashboard pack |
| DashboardPackAssignment | Runtime / packages | packages | |
| DashboardTemplate | Runtime / dashboard | platform_runtime | |
| TenantLayoutAssignment | Runtime / dashboard | platform_runtime | |

---

## apps/siteconfig/models_workflow.py

| Model | Target bounded context | Target app | Notes |
|-------|------------------------|------------|--------|
| WorkflowPack | Runtime / packages | packages | 10.7 Workflows |
| WorkflowPackAssignment | Runtime / packages | packages | |
| WorkflowTemplate | Runtime / workflows | platform_runtime or packages | |
| TenantWorkflow | Runtime / workflows | platform_runtime | |
| WorkflowRunLog | Runtime / workflows / orchestration | platform_runtime or orchestration | 4.1 orchestration |

---

## Migration order (for 1.2)

1. **Low-dependency first:** ThemePack, BrandProfile, BrandSettings, DesignTemplate → brand_experience.
2. **Plans:** Plan, PlanAddon, SystemFeature → plans.
3. **Runtime defaults:** Add platform_runtime.Defaults (or equivalent); backfill from SiteSettings; switch get_effective_site_settings to read from runtime.
4. **Dashboard/feature control:** Dashboard* and FeatureToggle* → platform_runtime (or split dashboard pack to packages).
5. **Workflow/orchestration:** WorkflowRunLog + new orchestration app for long-running processes.
6. **Remaining** by dependency order; Webhook* → apicenter when 8.1 lands.

---

**Next:** 1.2 state-safe migrations (create target tables, backfill, switch reads); 1.3 delete legacy paths after all call sites updated.
