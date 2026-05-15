# Multi-tenancy architecture — source of truth

> **Read this when:** a customer / security reviewer / auditor asks
> *"how do you keep tenants from seeing each other's data?"* — or
> before changing anything in the tenant-routing, RLS, or
> `dedicated_db_alias` paths.

Last updated: 2026-05-15 (v2.24 closeout — five-gap-plan Waves A–E + Gap-closure sweep).

## TL;DR

RunMyCampus is a **shared-schema multi-tenant SaaS** with three layers of
defense:

1. **Postgres Row-Level Security (RLS)** — the database enforces
   `school_id = current_setting('app.current_school_id')` on every row
   read/write. App code that bypasses the ORM (raw SQL) still hits this
   filter unless run under the explicit `BYPASSRLS` role.
2. **Architectural CI gate** — `scripts/scan_tenant_queryset_safety.py`
   requires `school=` / `school_id=` / `school__isnull=` kwargs on every
   `.filter` / `.get` / `.all` / `.update` / `.delete` against
   tenant-scoped models. Baseline-tracked (currently 741, burning down).
3. **Operational isolation tier** — tenants on the *Sovereign* / regulated
   SKU get a `School.dedicated_db_alias` pointing at a separate Postgres
   instance. The existing `TenantDatabaseRouter` already routes them.

No single layer is trusted alone. A leak requires all three to fail.

## The three layers in detail

### Layer 1 — Postgres RLS

* Migration: [`apps/schools/migrations/0048_force_rls_on_all_enabled_tables.py`](../apps/schools/migrations/0048_force_rls_on_all_enabled_tables.py)
  enables RLS on every tenant-scoped table with `FORCE ROW LEVEL
  SECURITY` so even table owners are filtered.
* Policy: each row visible to a session iff
  `school_id = current_setting('app.current_school_id')::uuid`.
* Session variable owner: [`apps/schools/rls_context.py`](../apps/schools/rls_context.py)
  exposes `set_current_school_id`, `reset_current_school_id`,
  `set_rls_bypass_on`, `reset_rls_bypass_var` as context managers.
* Request wiring: [`apps/schools/middleware.py`](../apps/schools/middleware.py)
  sets the session GUC at request entry and resets it at exit.
* Background-job wiring: Celery tasks and management commands that touch
  multiple tenants use `set_rls_school_id` as a context manager per
  tenant batch.

### Layer 2 — Architectural CI gate

* Scanner: [`scripts/scan_tenant_queryset_safety.py`](../scripts/scan_tenant_queryset_safety.py)
* Workflow: `.github/workflows/tenant-isolation-scan.yml`
* Baseline: `var/security-audit-baseline-tenant-isolation.json` — current
  count 741. Burning down; never silently increased.
* Allowlist mechanism: `# tenant-isolation-allow: <reason>` comment on
  the same line as the queryset. Used sparingly for legitimate
  cross-tenant operations (digests, observability, platform analytics).
* Companion scanner (Gap-closure sweep, 2026-05-15):
  [`scripts/scan_rls_bypass.py`](../scripts/scan_rls_bypass.py) — flags
  raw-SQL paths (`.raw()`, `.extra()`, `connection.cursor()`,
  `RawSQL(`) that don't sit inside a `set_rls_school_id` context
  manager or carry an `# rls-bypass-allow: <reason>` comment.

### Layer 3 — Dedicated-DB tier

* Field: `School.dedicated_db_alias` (`apps/schools/models.py`).
* Router: [`apps/siteconfig/db_router.py`](../apps/siteconfig/db_router.py)
  inspects the active tenant on every read/write and routes to the
  alias when set; falls back to `regional_cluster`; falls back to
  `default`.
* When used: regulated industries (EU public-sector tenants, healthcare
  partnerships) where contractual obligation requires "physical
  separation of tables". Tenants on the standard SKU share the
  `default` connection and rely on RLS.
* Data-residency overlay (Wave E, 2026-05-15):
  `School.data_region` (regulatory) is distinct from
  `regional_cluster` (operational). The
  [`verify_data_residency`](../apps/schools/management/commands/verify_data_residency.py)
  management command surfaces drift, and the
  [`DataResidencyMiddleware`](../apps/schools/middleware_residency.py)
  soft-logs every per-request mismatch (or hard-raises
  `CrossRegionWriteError` when `DATA_RESIDENCY_ENFORCE=True`).

## Common questions

### "Doesn't shared schema mean tenants can see each other's data?"

No. The Postgres RLS policy is enforced **before any rows are returned
to the app process**. A missing `WHERE` clause in app code is filtered
by the database, not by Python. The only ways to bypass RLS are:

1. Run as the owner role with `BYPASSRLS` — restricted to migrations,
   admin tasks, and the `set_rls_bypass_on` context manager, all
   audited.
2. Disable the policy via DDL — requires owner role + explicit `ALTER
   TABLE ... DISABLE ROW LEVEL SECURITY`. Caught by post-deploy probe
   in `scripts/run_security_self_audit.py`.

### "What's the worst-case leak path?"

A SQL-injection vulnerability **and** the injection runs as the owner
role **and** the injection successfully sets `app.current_school_id` to
another tenant's UUID. We mitigate each:

* SQL injection: ORM is the standard surface; raw-SQL is rare and now
  scanner-tracked.
* Owner role: never used inside request paths. Web tier connects as
  `rmc_app`, a role explicitly without `BYPASSRLS`.
* Session-variable spoofing: the GUC is set by middleware from the
  authenticated host header / JWT, not from a request parameter. The
  pentest SOW covers JWT-claim-vs-path-slug mismatch testing.

### "Why not schema-per-tenant for hard isolation everywhere?"

Trade-off audit (lives in `docs/CSS_RETIREMENT_DOCKET.md`, v2.24
five-gap-plan closeout):

| Concern | Schema-per-tenant | Shared + RLS (current) |
|---|---|---|
| Cross-tenant leak via app bug | Impossible at DB | Possible only if RLS *and* scanner *and* code review all fail |
| One ALTER TABLE at 10k tenants | N × seconds (hours) | Once, seconds |
| `pg_catalog` performance at 10k+ schemas | Degrades | Unaffected |
| Cross-tenant analytics | UNION N schemas | One query |
| Per-tenant custom columns | Possible (messy) | DynamicFieldDefinition (87-recipe catalog) |
| "Physically separated tables" compliance ask | Built-in | Dedicated-DB tier |

Decision: shared + RLS for the standard SKU; dedicated DB as a paid
escape hatch. Same architecture Salesforce, Shopify, Stripe, GitLab
Cloud run.

### "How do I add a new tenant-scoped model?"

1. Inherit from `apps.schools.models.TenantScopedModel` (or include a
   `school = models.ForeignKey("schools.School", ...)`).
2. The post-migration hook in [`apps/schools/management/commands/sync_rls_policies.py`](../apps/schools/management/commands/sync_rls_policies.py)
   picks it up and emits the RLS policy DDL on next deploy.
3. Run the scanner locally:
   `python scripts/scan_tenant_queryset_safety.py` — your new
   model's querysets must pass.
4. Add at least one isolation test exercising both happy-path and
   cross-tenant denial (see
   `apps/schools/tests/test_multi_tenant_isolation.py` for the
   pattern).

### "What if a customer asks for SOC 2 / HIPAA / FedRAMP?"

Today: shared-schema + RLS meets SOC 2 Common Criteria 6 (Logical
Access). For HIPAA Business Associate Agreements requiring "physical
isolation" of PHI, route to the dedicated-DB tier. FedRAMP requires
additional infrastructure (FedRAMP-authorized cloud region + provider
controls); out of scope for this doc.

## Files that touch this surface

| Concern | File |
|---|---|
| RLS policy DDL | [`apps/schools/migrations/0048_force_rls_on_all_enabled_tables.py`](../apps/schools/migrations/0048_force_rls_on_all_enabled_tables.py) |
| RLS session-variable context manager | [`apps/schools/rls_context.py`](../apps/schools/rls_context.py) |
| Request-time RLS middleware | [`apps/schools/middleware.py`](../apps/schools/middleware.py) |
| Per-tenant DB routing | [`apps/siteconfig/db_router.py`](../apps/siteconfig/db_router.py) |
| Data residency derivation | [`apps/schools/data_residency.py`](../apps/schools/data_residency.py) |
| Data residency enforcement | [`apps/schools/middleware_residency.py`](../apps/schools/middleware_residency.py) |
| Tenant-isolation scanner | [`scripts/scan_tenant_queryset_safety.py`](../scripts/scan_tenant_queryset_safety.py) |
| RLS-bypass scanner | [`scripts/scan_rls_bypass.py`](../scripts/scan_rls_bypass.py) |
| Pentest SOW (RLS scope) | [`PENTEST_SOW_2026_05_14.md`](PENTEST_SOW_2026_05_14.md) §"RLS bypass attempts" |
| Isolation test pattern | [`apps/schools/tests/test_multi_tenant_isolation.py`](../apps/schools/tests/test_multi_tenant_isolation.py) |
| Tenant-isolation scanner doc | [`TENANT_ISOLATION_SCANNER.md`](TENANT_ISOLATION_SCANNER.md) |

## What this doc is **not**

* Not a substitute for the pentest SOW — vendors should still test the
  RLS bypass path end-to-end.
* Not a runbook for adding a new region replica — that lives in
  `docs/compliance/DATA_RESIDENCY_LEGAL_GUIDE.md`.
* Not a marketing collateral page — written for engineers, auditors,
  and customer-trust reviewers.
