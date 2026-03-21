# Admin vs Super Responsibility Matrix

This document classifies every model registered in Django admin as **platform-only** (manager host `/admin/` only), **tenant-only** (tenant host `/admin/` only), or **both** (super-first governance in `/super/`, raw CRUD in both admin surfaces where applicable).

## Classification rules

- **Platform-only:** Models that must appear only on manager host `/admin/` (Platform Backoffice). E.g. platform config, migration runs, observability, billing platform models, marketplace catalog, provider/registry records, blueprint/policy/workflow/dashboard pack records that are platform-managed.
- **Tenant-only:** Models that must appear only on tenant `/admin/`. E.g. school-scoped data: per-tenant users, academics, evals, finance, portal, people, etc.
- **Both:** Super-first but admin-backed: catalog/maintenance on platform admin, tenant config on tenant admin. E.g. ThemePack, ReportTemplate, WorkflowPack, DashboardPack, SiteSettings, Integration.

## Matrix by app

| App | Model | Classification | Notes |
|-----|-------|----------------|-------|
| **accounts** | User | tenant | Per-tenant users |
| accounts | AccessRole | tenant | |
| accounts | Permission | tenant | |
| accounts | TemporaryRoleGrant | tenant | |
| accounts | Group | tenant | |
| accounts | UserPreference | tenant | |
| accounts | Delegation | tenant | |
| accounts | DelegationActionLog | tenant | |
| accounts | SecurityAuditLog | tenant | |
| accounts | UserPasskey | tenant | |
| **people** | (all models) | tenant | InformationTag, TeacherProfile, StudentProfile, etc. |
| **academics** | (all models) | tenant | AcademicYear, Term, Department, Subject, etc. |
| **evals** | (all models) | tenant | TeacherAssignment, Evaluation, GradeAudit, etc. |
| **reports** | (all models) | tenant | TermPublishStatus, ReportCard, PromotionRule, EMISSubmission |
| **finance** | (all models) | tenant | Per-tenant finance |
| **payroll** | (all models) | tenant | Per-tenant payroll |
| **portal** | (all models) | tenant | DocumentCategory, Event, Announcement, FAQ, KB, etc. |
| **communication** | (all models) | tenant | Message, Announcement, FeedItem, OutboundMessageQueue |
| **compliance** | (all models) | tenant | Per-tenant compliance |
| **requests** | (all models) | tenant | AccessRequest, RequestDecision, RequestAudit |
| **analytics** | BenchmarkAggregate | tenant | Per-tenant analytics |
| **apicenter** | APIAuditLog | tenant | Per-tenant API audit |
| **school_events** | (all models) | tenant | EventVenue, SchoolEvent, EventRegistration, etc. |
| **schools** | School | platform | Tenant registry (manager only) |
| schools | SchoolMembership | platform | Platform assigns users to schools |
| schools | SchoolProvisioningEvent | platform | |
| schools | TenantQuotaLimit | platform | |
| schools | TenantApiUsage | platform | |
| schools | Campus | tenant | Per-school |
| schools | Route, Stop, Bus | tenant | Per-school |
| schools | Hostel, HostelRoom | tenant | Per-school |
| schools | CanteenMeal | tenant | Per-school |
| schools | HealthRecord | tenant | Per-school |
| schools | BiometricDevice, BiometricAttendanceLog | tenant | Per-school |
| schools | LibraryItem, LibraryLoan | tenant | Per-school |
| schools | InventoryItem | tenant | Per-school |
| **observability** | (all models) | platform | SystemHealthMetric, PlatformIncident, etc. |
| **billing** | (all models) | platform | BillingAccount, TenantSubscription, UsageMeter, etc. |
| **automation** | (all models) | platform | AutomationExecutionLog, MigrationProfile, MigrationRun, etc. |
| **registries** | (all models) | platform | CountryRegistry, EducationLevelRegistry, etc. |
| **marketplace** | (all models) | platform | PublisherOrganization, MarketplaceApp, MarketplaceListing, etc. |
| **policies** | CountryProfile | platform | Global catalog |
| policies | BlueprintPack | platform | |
| policies | BlueprintCompatibilityRule | platform | |
| policies | PolicyCompatibilityRule | platform | |
| policies | PolicyBundle | tenant | Per-school bundle instance |
| policies | TenantBlueprint | tenant | Per-school |
| policies | TenantPolicyOverride | tenant | Per-school |
| policies | ScheduledPolicyOverride | tenant | Per-school |
| **siteconfig** | SiteSettings | tenant admin + **super** | **Platform:** `register_tenant_admin` only; manager uses `super:site_settings_list` / `super:site_settings_edit`. **Tenant:** Django admin unchanged. Resolvers: `apps/siteconfig/staff_navigation.py`. |
| siteconfig | ThemePack | both | Catalog (platform) / usage (tenant) |
| siteconfig | ReportTemplate, OfficialReportTemplate | both | |
| siteconfig | ReportCardStyle, ReportCardStyleAssignment | both | |
| siteconfig | Integration | both | |
| siteconfig | UserPreference | tenant | Per-user (siteconfig duplicate with accounts?) |
| siteconfig | RegionConfig | platform | Global regions |
| siteconfig | EducationSystemProfile | platform | Global |
| siteconfig | GradingScaleConfig, HolidayCalendar, WeatherLocation | both | |
| siteconfig | FeatureToggleDefinition, FeatureToggleState | both | |
| siteconfig | TourStep, FeatureUsageEvent | both | |
| siteconfig | Plan, PlanAddon | platform | Billing catalog |
| siteconfig | CountryMultiplier | platform | |
| siteconfig | RegionalAIConfig, AIModelRegistry | platform | |
| siteconfig | RevenueSnapshot, BillingWaiverAuditLog | platform | |
| siteconfig | WaiverRequest | platform | |
| siteconfig | CustomNuance, PendingNuance | platform | |
| siteconfig | CustomFeatureTicket, FeatureFragment | platform | |
| siteconfig | DesignTemplate, BrandProfile, BrandSettings | both | |
| siteconfig | GlobalBrandRegistry | platform | |
| siteconfig | DashboardUserPreference | tenant | Per-user |
| siteconfig | SuperAdminDashboardPreference | platform | |
| siteconfig | DashboardWidget, DashboardLayout, DashboardTemplate | both | |
| siteconfig | TenantLayoutAssignment | tenant | Per-tenant |
| siteconfig | WorkflowTemplate | both | Catalog / tenant usage |
| siteconfig | TenantWorkflow | tenant | Per-tenant |
| siteconfig | WorkflowRunLog | both | |
| siteconfig | WorkflowPack, WorkflowPackAssignment | both / tenant | Pack catalog (platform), assignment (tenant) |
| siteconfig | DashboardPack, DashboardPackAssignment | both / tenant | Same |
| siteconfig | FeatureControlAudit | platform | |
| siteconfig | ServiceIntegration | both | |
| siteconfig | DynamicFieldDefinition, DynamicFieldValue | tenant | Per-tenant |
| siteconfig | GlobalSyllabus, LearningPassport | both | |
| siteconfig | BreakGlassOverride | platform | |
| siteconfig | BroadcastCampaign | platform | |
| siteconfig | ProductFeedback, MarketingContent, BlogPost | platform | |
| siteconfig | TenantAdmissionNumberPolicy | tenant | Per-tenant |
| siteconfig | SyncConflict | platform | |

## Registration helpers

- `register_tenant_admin(model, admin_class)` — register only on `tenant_admin_site`.
- `register_platform_admin(model, admin_class)` — register only on `platform_admin_site`.
- `register_both(model, admin_class)` — register on both sites (same ModelAdmin). Use `register_both(model, tenant_admin_class, platform_admin_class)` for different classes.

See [ADMIN_REGISTRY_TECHNICAL_NOTE.md](ADMIN_REGISTRY_TECHNICAL_NOTE.md) for how to add new models and which site(s) to register to.
