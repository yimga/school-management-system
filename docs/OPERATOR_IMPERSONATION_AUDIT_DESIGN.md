# Operator ↔ tenant audit & control (Prompt 2, target #4) — design

Status: **Phase 1 + Phase 2 shipped. Phase 3 designed, not built.**

## Problem

When a platform operator acts inside a tenant (impersonation), we must be able to
answer, forensically: **who did what, in which tenant, and were they impersonating?**
The audit said this was a "gap — impersonation session-based, no persistent
who-did-what ledger." Investigation refined that into three precise facts:

1. **`ImpersonationLog`** (`apps/siteconfig/models_global_experience.py`) records only
   session **boundaries** — `SWITCH` / `END` — plus reason/IP/read-only/peer approver.
   It never records the **actions** taken during the session.
2. **`AuditLog`** (`apps/compliance/models_audit.py`) already auto-records every
   `CREATE` / `UPDATE` / `DELETE` (with field-level deltas) via `post_save`/`post_delete`
   signals for any model with `audit_enabled = True` — but the signal handlers
   **never set `user`**, so every model-mutation row was written `user=None`. The trail
   captured **WHAT but not WHO**, platform-wide.
3. **`MigrationCloudAuditEvent`** is a pristine hash-chained append-only ledger, but
   scoped to the migration domain only.

**Key implementation fact:** during impersonation, `request.user` is **the operator
itself** — it is *not* swapped to a tenant user. The impersonated tenant is carried in
`request.session["impersonation"] = {school_id, actor_id, read_only}`
(`apps/accounts/views_impersonation.py`). So attributing a mutation to `request.user`
already names the operator; the only missing dimension is the *"during impersonation of
school X"* flag.

ORM signals cannot see the request, but the observability middleware already publishes
the acting user + tenant via a `ContextVar` (`apps/observability/logging_context.py`).
That contextvar is the bridge the audit signals read.

## Phase 1 — actor-aware mutation audit  ✅ shipped (`118630021`)

- `logging_context.get_current_user_id()` exposes the request actor to non-request code.
- `compliance/signals._current_actor_id()` reads it and sets `AuditLog.user` on the auto
  CREATE/UPDATE/DELETE rows. System / management-command / migration writes (no request
  context) stay `user=None`, unchanged.
- Lock: `apps/compliance/tests/test_audit_actor_attribution_unit.py` (no-DB, mocked).
- Effect: impersonation-time mutations are now attributed to the operator automatically
  (request.user is the operator).

## Phase 2 — impersonation provenance  ✅ shipped (this batch)

- `logging_context`: `_during_impersonation_ctx` + `_impersonated_school_id_ctx`
  contextvars, `set_impersonation_logging_context()`, and getters.
- `observability/middleware.py`: reads `request.session["impersonation"]` in
  `process_request` and sets the contextvar (best-effort, never breaks the request).
- `compliance/models_audit.AuditLog`: two additive fields — `during_impersonation`
  (BooleanField, indexed) + `impersonated_school_id` (CharField). Migration
  `0023_auditlog_impersonation_context` (pure AddField, no backfill — existing rows take
  defaults).
- `compliance/signals._impersonation_audit_fields()` stamps both onto each audit row
  when impersonating; returns `{}` otherwise so the model defaults apply unchanged.
- Lock: `apps/compliance/tests/test_audit_impersonation_stamp_unit.py` (no-DB, mocked) +
  `makemigrations --check` clean (migration matches model).
- **ciPending:** the migration *apply* and a DB-backed end-to-end test (operator mutates
  a tenant row while impersonating → AuditLog row has user=operator,
  during_impersonation=True, impersonated_school_id=that tenant). Verify on Postgres CI.

### Follow-on (not built): assist_dock impersonation
A second impersonation system exists (`apps/assist_dock/`, grant + session based). Its
sessions could set the same contextvar from its own middleware so its mutations are
stamped identically. Small, additive, same pattern.

## Phase 3 — enforcement  ⏳ designed, NOT built

Two enforcement gaps remain. Both are **request-path / security-critical** and should be
built where Postgres CI + Playwright can verify, not merged unverified.

### 3a. Enforce `read_only` impersonation
Today `read_only` is captured into the session and logged, but **nothing blocks writes**
during a read-only session (no middleware checks it). Design:

- A thin middleware (or an extension of the existing impersonation middleware) that, when
  `request.session["impersonation"]["read_only"]` is true, rejects unsafe HTTP methods
  (`POST`/`PUT`/`PATCH`/`DELETE`) with `403` — except an allowlist (logout, end-
  impersonation, CSRF/asset paths).
- Defense-in-depth: a `pre_save`/`pre_delete` guard keyed on the
  `during_impersonation` + `read_only` contextvar that raises on a write attempt, so a
  non-HTTP path can't bypass the method check.
- Lock: a new CI gate / test asserting a read-only impersonated POST to a tenant write
  view returns 403 and writes no row.
- **Risk:** false-positive blocking of legitimate operator support actions. Needs the
  allowlist tuned against real operator workflows + Playwright coverage. Hence deferred.

### 3b. Superuser-bypass consent trail
A raw Django superuser can reach a tenant without the JIT consent check that
`OperatorTenantAssignment`-scoped operators go through
(`apps/schools/super_views_impersonation.py`). Design:

- Route the superuser path through the same consent check (or, at minimum, record an
  explicit `ImpersonationLog`/audit row marking `consent=bypassed-superuser` with reason),
  so superuser access is never silent.
- Lock: a test asserting a superuser switch without consent emits the bypass audit row.

## Why the staging
`AuditLog` is append-only and platform-wide; a migration into it and request-path write-
blocking are exactly the changes that warrant Postgres-CI verification before merge. Phase
1 + 2 are additive and no-DB-lockable, so they ship now; Phase 3 changes request behavior
and is documented here for a verifiable session.
