# apps/marketplace

> The governed app marketplace: catalog, publishers, scoped installs, webhooks,
> and the monetization ledger behind them.

**Tenancy:** SHARED (public schema; rows are scoped by an explicit `school` reference, not by a Postgres schema)
**Scale:** 20 models · 15 migrations · 49 test modules · ~19.7k LOC

## What this app owns

Marketplace is the platform's extension boundary. It owns the app catalog and
its semver release history, the publisher organizations that ship those apps and
the review queue that certifies them, the per-tenant installation with its
OAuth-style scope grants, outbound webhooks to publishers, and the ledger that
splits revenue between the platform and the publisher pool.

The decision that explains the shape of this app is the tenancy line above.
Marketplace is **control-plane state living in the public schema**, not tenant
state — one catalog, one publisher registry, one review queue serves every
school. But installs, scope grants, ratings, billing rows, and audit entries are
inherently per-school, so those models carry an explicit `school` foreign key
instead of relying on schema isolation. That means **nothing here gets tenant
isolation for free.** `sandbox.safe_queryset_for_app` is the guard: it returns
`none()` when `request.school` is unset, and when the caller authenticated with
an app API key it additionally cross-checks that the key's installation belongs
to the same school — the check that blocks cross-tenant escalation.

The second decision is least privilege. An app does not get ambient access; it
declares `AppScope` rows against the `scopes_catalog` vocabulary
(`<resource>:<access>`, where read/write/admin have documented meanings), a
tenant admin approves them into `ScopeGrant` rows at install, and
`permissions_runtime` resolves what a given API key may actually do. The
install-dialog copy lives in the catalog and is written to be approval-ready in
FERPA / GDPR data-rights language, because it is the text an admin legally
consents to.

## Key models

The 14 that matter most, of 20 declared.

| Model | Table | Purpose |
| --- | --- | --- |
| `MarketplaceApp` | `marketplace_marketplaceapp` | Catalog entry for an installable app (first-party, or third-party later) |
| `AppVersion` | `marketplace_appversion` | Published semver release of an app |
| `AppVersionCompat` | `marketplace_appversioncompat` | Compatibility matrix: platform min version, app min/max |
| `AppInstallation` | `marketplace_appinstallation` | A school has installed an app; carries config + status |
| `AppScope` | `marketplace_appscope` | Permission scope an app declares (OAuth-style least privilege) |
| `AppPermissionScope` | `marketplace_apppermissionscope` | Platform catalog entry for a scope string; maps to `AppScope.scope_code` |
| `ScopeGrant` | `marketplace_scopegrant` | What this app is actually allowed to do **at this school**, after admin approval |
| `AppAuditLog` | `marketplace_appauditlog` | Install / uninstall / scope-grant trail |
| `PublisherOrganization` | `marketplace_publisherorganization` | Verified publisher; unverified → pending → verified → suspended |
| `PublisherSignupRequest` | `marketplace_publishersignuprequest` | Self-serve registration awaiting operator review |
| `MarketplaceListing` | `marketplace_marketplacelisting` | Control-plane listing state: review, certification, revenue share |
| `MarketplaceReview` | `marketplace_marketplacereview` | Queue item for listing / security / certification / version review |
| `WebhookEndpoint` | `marketplace_webhookendpoint` | Publisher-declared endpoint for an app's topics |
| `WebhookDelivery` | `marketplace_webhookdelivery` | One HMAC-signed delivery attempt, with backoff retry state |

Monetization is carried by `TenantMarketplaceSubscription`, `AppBillingLedger`,
`MarketplaceMonetizationLedgerEntry`, and `PlatformMarketplaceEarning`;
`AppRating` and `CapabilityRegistry` round out the twenty.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `sandbox` | `safe_queryset_for_app` — the cross-tenant guard for app-authenticated requests |
| Module | `middleware` | Attaches `request.app_api_key` / `app_installation` / `app_scope`; session-only requests leave them unset |
| Module | `permissions`, `permissions_runtime` | Install/activate/scope SOT; runtime scope resolution for tenant API keys |
| Module | `scopes_catalog`, `scope_normalize` | Declarative scope vocabulary + code normalization |
| Module | `lifecycle` | Install / upgrade / downgrade / rollback ordered by semver |
| Module | `activation_orchestrator` | Applies capability bindings on sandbox → active; reverts on uninstall |
| Module | `capability_contract` | Every first-party app must declare how install changes tenant runtime |
| Module | `manifest_schema` | Read models for catalog + governance; `app_key` mirrors `MarketplaceApp.slug` |
| Module | `webhooks` | HMAC-signed dispatch with exponential-backoff retry |
| Module | `settlement_truth`, `settlement_state_machine` | Canonical settlement phase labels + legal-transition validator |
| Module | `monetization`, `monetization_ledger_ops` | Pricing hooks, add-on subscriptions, platform fee splits, metering |
| Module | `publishing_guards`, `trust`, `publisher_access` | Listing rules, verification/certification, publisher gating |
| Module | `semver_utils` | Strict semver comparison, no third-party dependency |
| Module | `install_impact` | Package/scope/compatibility preview shown before a sandbox install |
| Celery | `webhook_deliver_due` | Drains due deliveries |
| Celery | `deliver_install_hooks_task` | Fires install hooks |
| Celery | `marketplace_health_check` | Health sweep (also a management command) |
| Command | `seed_marketplace_apps`, `seed_marketplace_scopes`, `seed_capability_registry` | Catalog + vocabulary seeding |
| Command | `create_sandbox_tenant`, `seed_marketplace_publisher_e2e_fixtures` | Sandbox / E2E fixtures |
| Command | `marketplace_report_updates` | Available-update reporting |
| Routes | `public_app_catalog_api`, `publisher_dashboard`, `governance_console`, `monetization_inspector`, `webhook_endpoints`, `signup_review_queue`, … | Public, publisher, and operator surfaces (`urls.py`, `tenant_urls.py`, `urls_developer_platform.py`) |

## Before you change this

- **This app is SHARED. Scope every query yourself.** There is no per-tenant
  schema here. Any new queryset over a `school`-bearing model must filter on the
  school, and any app-authenticated read should go through
  `sandbox.safe_queryset_for_app`, which fails closed (`none()`) when
  `request.school` is unset rather than leaking the whole table.
- **An API key's installation must belong to the requesting school.** That
  cross-check inside `safe_queryset_for_app` is the anti-escalation control, not
  a redundancy — a valid key for school A must not read school B.
- **Money here is Decimal, and the `money-float` gate is zero-tolerance.**
  `apps/marketplace/` is one of the paths that scanner covers: `float()` on an
  amount silently corrupts ledger sums. Intentional sites need an explicit
  `# money-float-allow: <reason>` marker.
- **Settlement labels must never imply "paid" without confirmation.** That is
  the stated contract of `settlement_truth`. Ledger rows move only along
  documented edges — request the move through
  `settlement_state_machine.assert_legal_transition` (or `is_legal_transition`)
  *before* writing the new event. Each edge maps to a real provider event
  (Stripe / Paystack / Flutterwave / aggregator); keep the edge set small.
- **Scope descriptions are consent text, not UI copy.** `scopes_catalog`
  descriptions are what a tenant admin approves in the install dialog and must
  stay approval-ready in FERPA / GDPR language. `sensitivity` mirrors
  `AuditLog.Sensitivity` and drives downstream audit tagging.
- **`lifecycle` records hook URLs but does not fetch them.** HTTP delivery is
  asynchronous and belongs to `webhooks` / `deliver_install_hooks_task`. Do not
  add a synchronous outbound call to the install path.
- **`manifest_schema` asserts nothing about third-party certification.** It is a
  read model. Certification state lives in `MarketplaceListing` /
  `MarketplaceReview`; do not treat a well-formed manifest as trust.
- **Every first-party catalog app must declare its capability contract** —
  which feature flags, packages, integration adapters, widgets, or extension
  hooks install/activate touches. `activation_orchestrator` reverts exactly what
  the contract declared, so an undeclared side effect will not be undone on
  uninstall.
