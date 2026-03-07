# RunMyCampus Gap Ledger

Last updated: 2026-03-06

**Closure and execution:** Placeholder/pending decisions and “what to do next” for sweep categories (scoped, deferred, roadmap, partial, optional, backlog) are tracked in **docs/architecture/IMPLEMENTATION_EXECUTION_PLAN.md** and **SWEEP_DONE_WHEN_SCOPED_DEFERRED_AND_SIMILAR.md**. All roadmaps and optionals are addressed and marked complete in **ROADMAP_AND_OPTIONAL_CLOSURE.md**. Seating chart and other placeholder surfaces are gated (e.g. enable_seating_chart_beta); see execution plan §7 and §11.

This file is the canonical closure ledger for the Shopify/AWS-style platform plan. Status values:

- `implemented`: shipped in code and covered by checks/tests in this repo
- `partial`: foundational code exists, but the platform target is not fully closed
- `pending`: not yet implemented in the active codebase

## Implemented in this tranche

### Canonical school identity
- `implemented`: new shared registries app with `CountryRegistry`, `SubdivisionRegistry`, `EducationLevelRegistry`, and `EducationSystemTypeRegistry`
- `implemented`: `School.country_code`, `School.subdivision`, `School.education_levels`, and `School.education_system_types`
- `implemented`: superadmin create-school flow now persists canonical country/subdivision/education taxonomy data
- `implemented`: registry seed and coverage commands

### Control-plane and tenancy guardrails
- `implemented`: tenant URLConf no longer mounts `/super/`
- `implemented`: schema-mode app matrix now includes registries, billing, student360, and metadata in shared apps
- `implemented`: Django system checks now fail on missing schema-mode platform apps
- `implemented`: auth cookies are host-only by default unless explicitly overridden

### Branding runtime consolidation
- `implemented`: `BrandProfile` is now the canonical tenant branding model
- `implemented`: central brand resolver in `apps/siteconfig/branding.py`
- `implemented`: tenant branding API, template context, and welcome email now resolve through the brand resolver

### Shared-model ownership fixes
- `implemented`: `AccessRequest` now carries `school` and `schema_name`
- `implemented`: `AutomationExecutionLog` and `AutomationApprovalQueue` now carry `school` and `schema_name`
- `implemented`: requests dashboard scopes to the active tenant school when tenant context exists

### Enforcement and regression coverage
- `implemented`: tests for tenant `/super/` isolation
- `implemented`: tests for canonical onboarding identity persistence
- `implemented`: tests for brand resolver precedence
- `implemented`: tests for request dashboard tenant scoping
- `implemented`: tests for schema app matrix coverage
- `implemented`: tests for platform incident manager surfaces
- `implemented`: tests for legacy webhook bridge sync and canonical SLO aggregation

### Canonical webhook runtime
- `implemented`: `apps.events.webhooks` is now the canonical outbound webhook runtime
- `implemented`: legacy `apps.siteconfig.webhook_delivery` imports now resolve to the canonical event stack instead of a second delivery authority
- `implemented`: finance aid disbursement now emits through the canonical event/webhook runtime
- `implemented`: canonical webhook delivery now supports scheduled retries, max attempts, replay, and the management-command dispatch path
- `implemented`: webhook runtime tests now assert against `apps.events` models, not the legacy `siteconfig` ledger

### Manager-plane auth isolation
- `implemented`: manager host now uses dedicated session and CSRF cookie names via middleware-level cookie aliasing
- `implemented`: manager host allowlist now blocks tenant backend paths such as `/authentication/backend/`
- `implemented`: ending impersonation now always returns the operator to the manager host control plane
- `implemented`: `api_v1` routes now resolve as the `api` module for global module access enforcement

### Control-plane dashboard revamp
- `implemented`: manager host dashboard is now a dedicated control-plane shell rather than a plain school list with utility cards
- `implemented`: control plane now exposes operator queue boards for approvals, incidents, billing exceptions, support backlog, and provisioning breaches
- `implemented`: manager dashboard now surfaces platform health, webhook migration drift, registry coverage, BrandProfile adoption, and tenant identity readiness in one place
- `implemented`: tenant registry inside the manager dashboard now supports dense per-tenant operational context, search, and state filtering

### Platform billing foundation
- `implemented`: `apps.billing` now contains first-class platform billing models: `BillingAccount`, `TenantSubscription`, `UsageMeter`, and `PlatformLedgerEntry`
- `implemented`: superadmin billing dashboard now shows platform subscription state, trial watchlist, and recent platform ledger activity
- `implemented`: school provisioning now seeds platform billing account/subscription records
- `implemented`: billing services and dashboard tests now cover platform billing model creation and ledger writes
- `implemented`: platform billing processors now support signed webhook ingestion plus provider-specific normalization for generic relay and Stripe-compatible events
- `implemented`: revenue-share payouts now execute through configured processor adapters, write sync events, open billing incidents on failure, and can be driven by `run_revenue_share_payouts`

### Placeholder surface gating
- `implemented`: enrollment forecast API is now disabled by default behind `enable_enrollment_forecast_api`
- `implemented`: intervention roadmap API stub is now disabled by default behind `enable_intervention_llm_roadmap`
- `implemented`: seating-chart placeholder UI is now disabled by default behind `enable_seating_chart_beta`
- `implemented`: tests now verify placeholder surfaces stay dark until explicitly enabled

### Marketplace governance
- `implemented`: publisher organizations, governed listings, listing/security/certification reviews, and revenue-share metadata now exist in `apps.marketplace`
- `implemented`: the install pipeline now blocks unapproved or kill-switched third-party apps before tenant installation
- `implemented`: manager host now exposes a marketplace governance console and operator review actions
- `implemented`: marketplace governance tests now cover manager rendering, review approval, and third-party install blocking

### School events domain
- `implemented`: `apps.school_events` now exists as a distinct tenant product app for venues, sponsors, events, ticket tiers, sponsorship commitments, and registrations
- `implemented`: tenant event hub/detail/registration routes now exist and are integrated into portal event aggregation
- `implemented`: school-events tests now cover tenant rendering, ticket registration, and tenant-scoped public event discovery

### Metadata compatibility adoption
- `implemented`: `apps.metadata.services` now provides a compatibility layer that merges dynamic metadata with legacy `custom_attributes`
- `implemented`: degree-audit GPA checks, financial-aid eligibility context, and GDPR export/scrub flows now use the metadata compatibility layer instead of raw JSON reads alone
- `implemented`: metadata service tests now cover dynamic-field override precedence and legacy-sync compatibility

### Automated incident ingestion
- `implemented`: health metric degradation and recovery now auto-open and auto-resolve `PlatformIncident` records
- `implemented`: high-severity compliance audit alerts and threat alerts now auto-open `PlatformIncident` records
- `implemented`: incident-ingestion tests now cover observability health incidents plus compliance security incidents

## Partial

### Control plane separation
- `partial`: `manager.runmycampus.com` remains the control-plane host
- `implemented`: manager host no longer mounts tenant app URLConfs for portal, finance, evals, reports, academics, communication, or KB surfaces
- `implemented`: manager URLConf now exposes manager-safe compatibility namespaces and redirects so the shared shell can render without reopening tenant applications on the manager host
- `partial`: manager and tenant planes now use separate cookie names and host-only scope, and the dashboard shell is explicitly control-plane themed, but some shared templates still carry compatibility links that should be replaced with manager-native destinations over time

### Geography and global readiness
- `partial`: country registry is deterministic and can seed 195+ countries from `pytz`
- `partial`: city/timezone coverage still depends on the current `GlobalGeoCatalog` dataset and optional dependencies for rich global city search
- `partial`: subdivision registry currently backfills from legacy `Province` data; ISO-complete subdivision coverage is still open

### Branding migration
- `partial`: runtime reads now prefer `BrandProfile`
- `partial`: legacy `School` branding fields, `BrandSettings`, and `branding_metadata` still exist for compatibility and migration inputs
- `partial`: PDFs, report rendering, and all email/document surfaces are not yet fully audited for complete `BrandProfile` cutover

### Shared data ownership
- `partial`: core request and automation records now have tenant ownership fields
- `partial`: not every producer path has been audited yet to guarantee those fields are always populated

### Eventing and webhook consolidation
- `partial`: control-plane observability still exposes legacy migration state, but retired legacy subscriptions no longer count toward operational SLO metrics
- `partial`: Django system checks now warn only when active or unsynced legacy webhook subscriptions still exist beside the canonical stack
- `implemented`: `retire_legacy_webhooks` now syncs legacy subscriptions into `apps.events` and deactivates the legacy producers
- `partial`: the duplicate `siteconfig` delivery runtime no longer owns live dispatch and legacy webhook subscriptions are no longer manageable from siteconfig admin, but the legacy models/data still exist during migration

### Platform incident management
- `partial`: `PlatformIncident` now exists as a shared-schema control-plane model
- `partial`: manager host now exposes a dedicated incident console plus incident status APIs
- `implemented`: platform billing lifecycle and processor-webhook ingestion now auto-create and auto-resolve billing/integration incidents in the manager control plane
- `implemented`: observability health metrics and compliance threat/audit alerts now auto-create platform incidents
- `partial`: deployment-specific and remaining operator/security sources are still not fully wired into the incident pipeline

## Pending

### Platform billing
- `partial`: platform billing domain models now exist and are wired into superadmin flows
- `implemented`: platform billing now stores normalized processor sync events, external customer/subscription references, and sync heartbeat data
- `implemented`: platform billing now has lifecycle automation for trial conversion, renewal charging, delinquency/suspension, and entitlement reconciliation back into school freeze state
- `implemented`: platform billing now includes management commands for importing processor snapshots and running lifecycle automation
- `implemented`: manager host now exposes a live platform billing processor webhook endpoint with provider-configured signature validation and incident escalation
- `implemented`: platform billing now exposes first-class revenue-share payout records and dashboard visibility for scheduled payout obligations
- `implemented`: platform billing now has a provider adapter contract with a real Stripe-compatible webhook/payout path plus a generic relay adapter for managed processors
- `partial`: additional provider adapters and payout-status reconciliation beyond relay/Stripe still need to be added as the processor catalog expands

### Metadata adoption
- `partial`: metadata compatibility layer now exists and covers degree audit, aid eligibility, and GDPR flows
- `partial`: remaining direct `custom_attributes` usage still needs to be migrated onto metadata services or removed

### No-hardcoding campaign
- `partial`: key placeholder/stub surfaces are now behind explicit flags instead of always-on routes
- `partial`: education template catalogs in the API and create-school flow now resolve from approved education profiles instead of only static preset lists
- `pending`: finish replacing country/template branching across reports, payments, integrations, and operator copy with registries, policies, or seeded config

### Stub burn-down
- `partial`: forecast, intervention-roadmap, and seating-chart placeholders are now dark by default
- `pending`: remove or isolate the remaining production-facing placeholder and compatibility surfaces called out in the platform audit
