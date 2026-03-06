# RunMyCampus Gap Ledger

Last updated: 2026-03-06

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

### Placeholder surface gating
- `implemented`: enrollment forecast API is now disabled by default behind `enable_enrollment_forecast_api`
- `implemented`: intervention roadmap API stub is now disabled by default behind `enable_intervention_llm_roadmap`
- `implemented`: seating-chart placeholder UI is now disabled by default behind `enable_seating_chart_beta`
- `implemented`: tests now verify placeholder surfaces stay dark until explicitly enabled

## Partial

### Control plane separation
- `partial`: `manager.runmycampus.com` remains the control-plane host
- `partial`: manager URLConf still mounts several tenant namespaces for reverse compatibility; these still need deliberate reduction or manager-only replacements
- `partial`: manager and tenant planes now use separate cookie names and host-only scope, and the dashboard shell is now explicitly control-plane themed, but the URLConf/template namespace split is still not fully reduced to manager-only surfaces

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
- `partial`: control-plane observability now aggregates both the legacy `siteconfig` ledger and the canonical `apps.events` ledger
- `partial`: Django system checks now warn when legacy webhook subscriptions still exist beside the canonical stack
- `partial`: a sync command now groups legacy webhook subscriptions into canonical `apps.events.WebhookSubscription` records
- `partial`: the duplicate `siteconfig` delivery runtime no longer owns live dispatch, but the legacy models/admin/data still exist and the observability dashboard still reports both ledgers during migration

### Platform incident management
- `partial`: `PlatformIncident` now exists as a shared-schema control-plane model
- `partial`: manager host now exposes a dedicated incident console plus incident status APIs
- `partial`: incident ingestion and automated creation from observability/security/billing signals are still open

## Pending

### Platform billing
- `partial`: platform billing domain models now exist and are wired into superadmin flows
- `partial`: platform billing still lacks external processor sync, automated invoicing lifecycle, entitlement reconciliation, and payout/revenue-share workflows

### Metadata adoption
- `pending`: replace remaining direct `custom_attributes` style usage with the metadata engine or an explicit compatibility layer

### School events domain
- `pending`: create a distinct tenant school-events product app for event operations, sponsorships, ticketing, and venues

### Marketplace governance
- `pending`: add publisher organizations, security review status, revenue share, payout workflows, and listing governance

### No-hardcoding campaign
- `partial`: key placeholder/stub surfaces are now behind explicit flags instead of always-on routes
- `pending`: finish replacing country/template branching across reports, payments, integrations, and operator copy with registries, policies, or seeded config

### Stub burn-down
- `partial`: forecast, intervention-roadmap, and seating-chart placeholders are now dark by default
- `pending`: remove or isolate the remaining production-facing placeholder and compatibility surfaces called out in the platform audit
