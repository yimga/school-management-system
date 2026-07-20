# apps/schools

> The tenant itself: what a school *is*, how a request finds one, how a new one
> gets provisioned, and the operator control plane that oversees the fleet.

**Tenancy:** SHARED (public schema — this app defines the tenant, so it cannot live inside one)
**Scale:** 20 models · 76 migrations · 291 test modules · ~114k LOC

## What this app owns

Everything upstream of "which school am I?". It owns the `School` row, the
host/domain resolution that maps `ghs-limbe.runmycampus.com` to it, the
membership that links a user to it, the provisioning pipeline that creates its
Postgres schema and seeds it, the data-residency rules that decide which region
its bytes may sit in, and the `super/` control plane an operator uses to run the
fleet. It also carries the public marketing surface (`marketing_*`) and the
self-service signup funnel, because both exist *before* a tenant does.

Two facts are load-bearing and neither is obvious from the app name:

**`School` is not the django-tenants tenant model.** `settings.TENANT_MODEL` is
`customers.Client` and `TENANT_DOMAIN_MODEL` is `customers.Domain`. `School` is
the platform's identity/business row in the public schema; `domain_sync.py` keeps
`School`, `SchoolDomain`, the legacy `School.custom_domain` fields, and the
django-tenants `Client`/`Domain` records consistent so that "verified" implies
"routable". If you are hunting for `schema_name`, it is on `Client`, not here.

**There are two tenancy modes, and this app straddles both.** `USE_DJANGO_TENANTS`
(derived from the DB engine, overridable via `TENANCY_MODE=SCHEMA|RLS`) picks
between schema-per-tenant and a single shared schema with Postgres row-level
security. `domain_sync.use_django_tenants()` is the SOT for that question in app
code; `rls.should_apply_rls()` is its mirror image and returns `False` whenever
schema mode is on. Middleware differs per mode too — `HealthAwareTenantMainMiddleware`
in schema mode, `TenantMiddleware` resolving `request.school` from the host in RLS
mode.

## Key models

20 models. `School` and its immediate satellites are the platform spine; the
Wedge-5 advancement/fundraising cluster is a self-contained tenant feature that
happens to live here because it hangs off `School`.

| Model | Table | Purpose |
| --- | --- | --- |
| `School` | `schools_school` | **The tenant.** One row per school, UUID pk, slug/subdomain identify it in the URL. Holds identity, branding, plan, and region; behaviour comes from `request.tenant_runtime`, and `settings`/`features` are storage only. |
| `SchoolDomain` | `schools_schooldomain` | Many hostnames per tenant (subdomain + custom). The Caddy ask-endpoint and middleware resolve a tenant from here; custom domains verify via a `dns_token` TXT record. |
| `SchoolMembership` | `schools_schoolmembership` | Links a user to a school with a role. A user may belong to several schools — never assume one. |
| `SchoolProvisioningEvent` | `schools_schoolprovisioningevent` | Audit trail for onboarding + domain-verification lifecycle. |
| `SignupVerification` | `schools_signupverification` | Email-verification token for self-service signup; the school is created on the far side of it. |
| `TenantInvite` | `schools_tenantinvite` | Operator-issued invitation for a *new* school to join the platform (not a user invite). |
| `TenantQuotaLimit` | `schools_tenantquotalimit` | Per-tenant API/quota limits for billing and fairness. |
| `TenantApiUsage` | `schools_tenantapiusage` | Per-tenant API usage feeding billing + the super-admin dashboard. |
| `TenantInteropAccessLog` | `schools_tenantinteropaccesslog` | OneRoster / interop API access audit: which token, which endpoint, from where. |
| `MarketingFunnelEvent` | `schools_marketingfunnelevent` | Full conversion funnel — anonymous *and* school-scoped, so it spans the pre-tenant world. |
| `FundraisingCampaign` | `schools_fundraisingcampaign` | Wedge 5: a tenant-scoped fundraising campaign / appeal. |
| `AdvancementDonor` | `schools_advancementdonor` | Wedge 5: per-school donor CRM (minimal v1 — gifts and receipts). |
| `AdvancementGift` | `schools_advancementgift` | A gift / receipt line tied to a donor. Monetary crediting is delegated to `finance.aid_services`. |
| `DonationPledge` | `schools_donationpledge` | A promise to give later — deliberately distinct from `AdvancementGift`. |
| `RecurringDonationSchedule` | `schools_recurringdonationschedule` | A donor's recurring giving commitment. The platform holds no card on file; read the model docstring before assuming auto-charge. |
| `InKindDonation` | `schools_inkinddonation` | A donated good/service; on acceptance it feeds the schoolops inventory register. |
| `GrantApplication` | `schools_grantapplication` | Wedge 5: an outbound grant the school applies for, tracked through its lifecycle. |
| `GrantMilestone` / `GrantReport` | `schools_grantmilestone`, `schools_grantreport` | Deliverables and filed reports against an awarded grant. |
| `DonorGiftAccessLink` | `schools_donorgiftaccesslink` | Signed magic-link grant so a donor can see their own gifts/receipts without an account. |

## Surfaces

This app has **no `urls.py`**. Its views are mounted from the host-split
urlconfs in `config/` — marketing + signup + section-8 views from `config/urls.py`,
and the whole operator console via `path("super/", include("apps.schools.super_urls", namespace="super"))`.

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `host_routing` | `normalize_host`, `is_public_host`, `public_host_kind`, `get_canonical_base_domain`. Reserved subdomains (`www`/`admin`/`api`/`manager`/…) can never be a tenant. |
| Module | `domain_resolution_service` | The one import surface for host/domain questions; re-exports `host_routing` + `tenant_url`. Use it instead of scattering `request.get_host()`. |
| Module | `domain_sync` | Keeps `School` / `SchoolDomain` / legacy fields / django-tenants `Client`+`Domain` consistent. `use_django_tenants()` lives here. |
| Module | `onboarding_service` | Schema-per-tenant onboarding: slug validation → schema create → tenant migrations → localized seed → first admin → domain register. Idempotent; kill-switch drops the schema on post-create failure. |
| Module | `provision_watchdog` | Resumes a provision whose runner was **killed** (see below). |
| Module | `control_plane` | Operator access contract for manager-host and `/super/` surfaces. Must not rely on tenant RBAC. |
| Module | `tenant_access` | `safe_queryset_for_school`, `user_belongs_to_school`, `has_school_permission` — post-auth tenant RBAC, fail-closed on a missing school. |
| Module | `data_residency` | `data_region` (regulatory) vs `regional_cluster` (operational), country→region map, `region_for_alias`. |
| Module | `conversion_lock_state` | First-value completion recorded explicitly in `school.settings`, never inferred from URLs. |
| Module | `tenant_schema_guard` | Detects and best-effort heals *missing tables* in a tenant schema (the fake-applied `CreateModel` case). |
| Module | `deletion` | Hard-deleting a `School` from `public`. Django's cascade collector walks all 328 tenant tables that FK `schools_school` and dies on the first one, so `PublicSchemaCollector` skips relations that live only in tenant schemas. A school that still owns a live schema cannot be deleted at all (those FKs are real, cross-schema) — `assert_deletable` refuses by name; `delete_school(school, drop_schema=True)` removes both together. |
| Module | `db_safety` | `savepoint_suppress` — the savepoint every swallowed database error needs. Postgres aborts the whole transaction on any statement error, so `except Exception: pass` around a query turns one recoverable failure into every later statement failing for an unrelated reason. Suppress inside a savepoint, and read `outcome.ok` instead of assuming success. |
| Module | `middleware_tenant_main` | `HealthAwareTenantMainMiddleware` — skips tenant lookup for health probes and returns a 200 "degraded" during Postgres blips so the dyno stays up. |
| Celery | `provision_school_task` | The provisioning job. |
| Celery | `reconcile_half_provisioned_tenants_task`, `detect_tenant_table_drift_task` | Durable reconcilers. |
| Celery | `run_scheduled_tenant_purges_task`, `purge_tenant_media_task` | Offboarding / wind-down. |
| Celery | `send_welcome_email_task`, `ensure_demo_environment_scheduled` | Signup + demo upkeep. |
| Command | `create_school`, `run_tenant_migrations`, `migrate_tenant_schemas_one_by_one`, `verify_tenant_provisioning` | Provisioning operations. |
| Command | `unstick_provisions`, `heal_tenant_schema_drift`, `detect_tenant_table_drift`, `tenant_health_check` | Repair operations. |
| Command | `verify_data_residency`, `verify_residency_readiness`, `verify_rls_readiness`, `verify_tenant_rls` | Isolation / residency readiness checks. |
| Command | `e2e_lifecycle` | End-to-end provisioning harness with zero-residue teardown. |
| Command | `tenant_wind_down`, `triage_signup_school`, `activate_pending_signup_schools` | Lifecycle + signup triage. |

## Before you change this

- **Liveness of a provision is judged by heartbeat staleness, not by status.**
  `provision_watchdog.py` documents the root cause at length and it is worth
  reading in full: the `tenant_schema` step runs a multi-minute blocking migrate,
  and when the process is *killed* (gunicorn's 120 s timeout, a worker recycle, an
  OOM) the kill is a signal — not a Python exception — so `finalize_run` never
  runs and Celery's retry never fires. The run is stranded `status="running"`
  forever. Every older heal path was gated on `status="stuck"`, which only a
  Celery **beat** sweep writes, and the default topology has no beat. Do not add
  another status-gated healer. Every resume is single-flighted through an atomic
  `cache.add` lock keyed on the school; the migrate is idempotent so each cycle
  makes forward progress.
- **`data_region` and `regional_cluster` are not the same field and must not be
  merged.** One is the legal/compliance answer, the other is the operational
  DB-alias answer. They agree almost always; the gap is exactly what makes a
  gradual region migration possible.
- **`School.tenant_hash` is derived, not free-form.** It is `sha256(str(id))[:12]`,
  stamped in `save()` and indexed so the WAL drain can resolve a tenant in O(1).
  The offline island sends this value; a client that hashes the *host* instead
  will be rejected. Rows predating the backfill fall back to a full scan.
- **`School.resolve_currency()` is the only sanctioned "what currency?" read** —
  explicit override → country pack → region → platform default, upper-cased ISO
  4217, never blank. A hardcoded literal or a bare `school.currency` read breaks
  local-first money and trips `scan_locale_display.py`.
- **Control-plane operator roles are env-only, on purpose.** `control_plane._operator_roles()`
  reads `CONTROL_PLANE_OPERATOR_ROLES` and nothing else. Routing it through the
  admin UI or RuntimeDefaults would let a compromised SUPERADMIN promote arbitrary
  roles to peer-operator with no code-or-deploy trail. Do not "improve" this into
  a database-backed setting.
- **`is_staff` is not an operator signal on this platform.** The platform mints
  `is_staff=True` tenant admins, so `@staff_member_required` on anything reachable
  from `config/tenant_urls.py` is not a gate. Use `require_control_plane_access`;
  `scan_staff_gate_on_tenant_surface.py` enforces it at baseline 0.
- **Conversion completion is recorded, never inferred.** `record_conversion_first_action`
  in `conversion_lock_state.py` is the only supported writer — call it from a model
  signal or a domain service. Do not re-derive first-value from URL heuristics.
- **Advancement is enabled-by-default and only an explicit `False` disables it.**
  It predates the opt-in feature-gate, so running it through the usual
  `is_feature_enabled` would lock out every existing tenant. There is no backfill
  migration; the absence of the key means on.
- **`onboarding_service` must stay idempotent.** It is retried. An existing
  `School`/`Client` skips creation, and a failure *after* schema creation triggers
  the kill-switch: delete the tenant and drop the schema, logging into the public
  schema. Any new step you add has to tolerate being run twice.
- **`tenant_schema_guard.ensure_models_tables()` is best-effort by contract.**
  Each model is created in its own savepoint with deferred FK SQL flushed in
  place, so one failure is logged and skipped and can never abort
  `migrate_schemas --tenant` or a deploy. Keep it that way — a heal that can break
  a deploy is worse than the drift it fixes.
- **A migration that never reached a tenant schema is this platform's recurring
  production failure class.** Missing *columns* are healed by the per-app
  `schema_repair.py` modules; missing *tables* by `tenant_schema_guard`. Before
  hand-rolling a third mechanism, check `migrate --plan` for an existing repair
  step.
