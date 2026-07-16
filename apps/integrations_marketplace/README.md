# apps/integrations_marketplace

> Outbound connectors (OAuth2, LMS, mail, chat), inbound webhooks, and the app
> marketplace / install metadata.

**Tenancy:** SHARED (public schema; most rows carry an explicit `school` FK rather than living in a tenant schema)
**Scale:** 18 models · 6 migrations · 28 test modules · ~20.3k LOC

## What this app owns

This app is the platform's edge: everything that talks to a system RunMyCampus
does not own. That means the OAuth2 dance and the token lifecycle that follows
it, the LMS connector family (PowerSchool, Blackboard, D2L, Schoology, Sakai,
itslearning, Clever, ClassLink, MS Teams EDU), inbound webhook receipt with a
retry FSM and a dead-letter queue, per-tenant email backend selection, and the
marketplace models that describe installable apps, scopes, and billing.

The organising decision is **no hardcoding: which credential to use is always
resolved, never assumed**. `resolver.py` walks a four-step cascade for any
(connector_slug, school, campus) tuple — per-campus row, per-school row, then up
the `School.parent_school` chain so a district configures Zoom once and children
inherit, and finally a platform env default. It returns a `ResolvedConnector`
dataclass rather than the raw model row, so call sites get a contract that
survives schema renames. School admins never type a `client_id`; they only
consent, and the platform-level credentials come from env.

The second decision is **honest maturity tiers**. `lms_connector_dispatcher` is
intentionally thin — it resolves a provider slug to a module and normalises the
op name, and it adds no audit, retry, or secret handling, because those belong in
the per-provider modules. When a SCAFFOLD-tier provider is asked for a live op it
returns a structured `{"status": "scaffold_only", ...}` instead of raising, so the
operator UI can render a maturity pill rather than crash. Several surfaces here
are explicitly scaffolds and say so — see "Before you change this".

## Key models

The 12 that matter most, of 18 declared. This table is not exhaustive.

| Model | Table | Purpose |
| --- | --- | --- |
| `ServiceIntegration` | `siteconfig_serviceintegration` | The per-school / per-campus connector row the cascade resolves to; credentials live in its `config`. |
| `Integration` | `siteconfig_integration` | Legacy per-school integration record driven by the operator-facing form schema. |
| `LMSConnectorToken` | `integrations_marketplace_lmsconnectortoken` | Per-(tenant, provider) OAuth2 access + refresh tokens. Fernet-encrypted at the field level. |
| `LMSPushGradeAudit` | `integrations_marketplace_lmspushgradeaudit` | One row per `push_grade` attempt; also carries the rotation-required paper trail. |
| `LMSDiagActionAudit` | `integrations_marketplace_lmsdiagactionaudit` | One row per force-refresh / force-rotate click in the operator console. |
| `WebhookDeadLetter` | `integrations_marketplace_webhookdeadletter` | Parked payload for a delivery that exhausted its retry budget. |
| `TenantRetentionOverride` | `integrations_marketplace_tenantretentionoverride` | Per-tenant override of an audit table's retention window. |
| `MarketplaceApp` / `MarketplaceListing` | `marketplace_marketplaceapp` / `marketplace_marketplacelisting` | The installable app and its storefront listing. |
| `AppInstallation` | `marketplace_appinstallation` | A tenant's install of a marketplace app. |
| `AppScope` / `ScopeGrant` | `marketplace_appscope` / `marketplace_scopegrant` | Declared scopes and what a tenant actually granted. |
| `CapabilityRegistry` | `marketplace_capabilityregistry` | Capability registry entries. |
| `AppBillingLedger` / `AppAuditLog` | `marketplace_appbillingledger` / `marketplace_appauditlog` | Marketplace billing entries and installation audit. |
| `PublisherOrganization` | `marketplace_publisherorganization` | The publisher behind a listing. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `refresh_due_lms_tokens` | Hourly proactive refresh inside the 24h window. |
| Celery task | `rotate_due_lms_tokens` | Daily 03:30 UTC; catches rows the refresh leg cannot fix. |
| Celery task | `auto_prune_revoked_lms_tokens` | Clears both tokens on `refresh_revoked`. |
| Celery task | `purge_due_lms_audit_rows`, `purge_due_lms_diag_action_rows` | Weekly retention purges. |
| Celery task | `refresh_due_oauth_tokens_task`, `fetch_due_mailboxes_task`, `renew_due_subscriptions_task` | Generic OAuth, mailbox fetch, push-subscription renewal. |
| Module | `beat_schedule` | Beat SOT; `install_lms_beat_schedule(app)` is called from `config/celery.py`. Idempotent, with per-entry env disable flags. |
| Module | `resolver` | The four-step connector cascade. |
| Module | `connector_registry` | Auth-flow metadata SOT (OAuth endpoints, scopes, brand). |
| Module | `webhook_retry_fsm` | Retry schedule SOT: 1m / 5m / 30m / 2h / 12h / 24h, then exhausted. |
| Module | `oauth` | The connect/callback dance and signed state payload. |
| Module | `middleware` + `celery_tenant_binding` | Per-tenant email backend binding for request and task flow. |
| Command | `verify_oauth_token_rotation_policy`, `refresh_oauth_tokens`, `check_marketplace_deps`, `check_brand_assets`, `fetch_mailboxes`, `subscribe_push`, `renew_push_subscriptions`, `apply_marketplace_migrations`, `export_sentry_alert_rules` | |
| URLs | `oauth_connect` / `oauth_callback`, `webhook_receiver`, `rotate_webhook_secret`, `hub`, `disconnect` / `disconnect_campus` / `bulk_disconnect`, `redirect_uri_registry`, and the `s10x_*` operator console family | |

## Before you change this

- **Middleware order is a contract, not a preference.** The tenant-email
  middleware must run **after** `apps.schools.middleware.TenantMiddleware` (which
  sets `request.school`) and **before** any view that may send mail synchronously.
  Without it, `_active_school()` never reaches its thread-local step and every
  in-request email silently goes through the global provider even when the tenant
  has its own connector row. The unbind in `process_response` is load-bearing:
  thread pools reuse threads, so a stale binding from request N poisons request N+1.
- **Celery tasks do not get the middleware.** Pass `school_id=...` in the task
  kwargs (explicit and serializable — the preferred pattern) or call
  `bind_tenant_for_email(school)` in the task body. The `task_prerun`/`task_postrun`
  hooks in `celery_tenant_binding` are the parallel of the middleware, and when
  Celery is not installed they simply never connect and the global settings apply.
- **`webhook_retry_fsm` is the single source of truth for the retry schedule.**
  The dispatch worker and the operator UI both import from it precisely so the
  schedule cannot drift. Do not re-declare the intervals at a call site.
- **Never log secret material.** `LMSConnectorToken` uses a Fernet-encrypted field
  so the DB column never holds plaintext bearer material (MultiFernet rotation:
  latest key writes, any key reads). `webhook_key_rotation` stages a new secret
  alongside the old during a grace window and is explicit that it never leaks
  secrets into logs or audit rows. Keep both properties when adding diagnostics.
- **`WebhookDeadLetter.payload_b64` is opaque on purpose.** The payload is never
  JSON-decoded at park time, because a malformed body may be *why* the delivery
  failed. Only `provider` / `event_type` / `last_error_reason` are queryable, so
  the payload cannot be accidentally indexed or rendered by a list-view template.
  Decode on replay, not on write.
- **Some surfaces are scaffolds and the code says so.** `lti_1_3_launch_verifier`
  performs real verification only when `cryptography` + `PyJWT` are installed and
  otherwise returns a `deps_missing` scaffold verdict; `xapi_caliper_emitter`
  assembles payloads but only sends when `RMC_XAPI_LIVE_OUTBOUND` /
  `RMC_CALIPER_LIVE_OUTBOUND` are set, returning `{status, format, would_send | sent, ...}`.
  Do not describe these as live integrations without flipping the gates.
- **Sweeps must never raise.** `lms_token_refresh`, `lms_oauth_auto_prune`, and
  `lms_retention_resolver` are all explicitly contract-bound to bound their failures
  and surface them per-row (the resolver falls back to env/default when the DB is
  unavailable, and defaults to 7 years for FERPA). A sweep that raises takes out the
  whole beat cycle for every tenant.
- **Beat entries are read at install time.** `install_lms_beat_schedule` preserves
  any pre-existing key so it never overwrites an operator's hand-written entry, and
  the per-entry `RMC_LMS_*_BEAT_DISABLED` flags are checked at install — changing one
  requires a worker restart, by design, since beat config is not hot-reloadable.
  The schedule being installed does not by itself mean a beat process is running;
  that is a deployment concern.
- **`webhook_handlers` is imported from `AppConfig.ready()`** so the
  `@register_webhook_handler` decorators run. If that import breaks, `WEBHOOK_HANDLERS`
  stays empty and the inbound receiver silently falls through to "no handler" / 204
  rather than erroring — a quiet failure mode worth remembering when a webhook
  "does nothing".
- **`connector_registry` vs `integration_catalog` is a real split.** The catalog
  describes what the operator types in (form schema + guardrails) for legacy
  `Integration` rows; the registry describes how the platform talks to the upstream
  (OAuth endpoints, scopes, brand). Registry fields are immutable per release and
  not operator-editable — they belong in code.
