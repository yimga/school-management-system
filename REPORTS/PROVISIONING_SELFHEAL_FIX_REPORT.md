# Provisioning self-heal fix — root cause, fix, and honest verification

**Date:** 2026-07-16
**Symptom:** School provisioning gets stuck at "Preparing your campus workspace" (the
`tenant_schema` step); status stays `active` forever, all later steps `pending`, and
self-healing does nothing.

---

## 1. Root cause (diagnosed, evidence-backed)

### 1a. Why it hangs
The `tenant_schema` step runs a full-app-set `migrate --run-syncdb` on the brand-new tenant
schema ([`onboarding_service.py:99`](../apps/schools/onboarding_service.py#L99), wrapped in
`heartbeat_during` at [`tasks.py:1110`](../apps/schools/tasks.py#L1110)). On a loaded
free-tier Postgres this routinely exceeds **120 s**.

That migrate frequently runs **inside the web dyno**, which kills it at 120 s:
- broker-down sync fallback in the request thread ([`tasks.py:629`](../apps/schools/tasks.py#L629));
- an in-process booster that runs the migrate even when the Celery task queued
  ([`tasks.py:665-668`](../apps/schools/tasks.py#L665-L668)) — can run **concurrently** with the
  worker (double-migrate on one fresh schema);
- a daemon thread in the web dyno ([`tasks.py:733-740`](../apps/schools/tasks.py#L733-L740));
- **Celery-eager mode** (the documented default topology: no broker → `CELERY_TASK_ALWAYS_EAGER`,
  so `.delay()` runs inline in the caller thread).

`GUNICORN_TIMEOUT` is **120 s** ([`render.yaml`](../render.yaml) / `render_start_web.sh:41`). A
SIGKILL is not a Python exception, so `_do_provision` never reaches `finalize_run` and the task's
`self.retry` never fires. The `WorkflowRun` is stranded `status="running"`, pinned at
`tenant_schema`, heartbeat frozen.

### 1b. Why self-healing did nothing (the decisive finding)
Every stuck→requeue recovery is gated on `status="stuck"`. **`is_stuck()` is a pure display
predicate — it never writes.** The only code that writes `status="stuck"` is a Celery-**beat**
sweep ([`platform_runtime/tasks.py:387`](../apps/platform_runtime/tasks.py#L387)), and that sweep
was **not registered in `periodic.py`** — the in-process "beat-without-a-worker" scheduler that
runs jobs off `/health/` ticks. Web-only deploy ⇒ sweep never fires ⇒ status never becomes
`stuck` ⇒ `try_auto_apply_on_stuck` bails `"not_stuck"` ⇒ no requeue.

Compounding gaps:
- `reconcile_half_provisioned_tenants` (the durable catch-all) is gated on `is_active` +
  `phase_a_complete`, both set only **after** `tenant_schema` — so it is structurally blind to a
  run that died **during** `tenant_schema`. It was also beat-only (dead in the no-beat topology).
- The lazy abandonment reaper needs ~3.3 h of a frozen heartbeat and only marks the run FAILED —
  it never resumes provisioning.
- A concrete latent bug: the backup requeue sweep ordered by `-updated_at`, a field `WorkflowRun`
  does not have → `FieldError`, swallowed → the sweep silently did nothing even with beat running.
- `_provisioning_job_in_flight` treats any `status="running"` row as in-flight — even one whose
  heartbeat died minutes ago — so it actively **blocked** re-kicking the exact runs that needed it.

---

## 2. The fix (implemented)

| # | File | Change |
|---|------|--------|
| 1 | **NEW** `apps/schools/provision_watchdog.py` | Canonical single-flighted resume. Judges liveness by **heartbeat staleness** (>120 s = 4 missed 30 s pings ⇒ process dead), cancels the zombie, re-drives via a background daemon thread. Idempotent migrate ⇒ each cycle makes forward progress. Atomic per-school cache lock + hourly cap prevent stampede/runaway. |
| 2 | `apps/platform_runtime/periodic.py` | Registered `schools.resume_stuck_provisions` + `schools.reconcile_half_provisioned_tenants` as **light `/health/`-tick jobs** → self-heal now fires **without Celery beat**. |
| 3 | `apps/platform_runtime/tasks.py` | Fixed `-updated_at` → `-started_at` (`FieldError` that no-op'd the backup requeue sweep). |
| 4 | `apps/schools/tasks.py` (`_do_provision`) | **Single-flight guard**: refuse a second concurrent drive when one is genuinely live (fresh heartbeat) — kills the double-migrate race and the "re-trigger a doomed inline migrate every poll" storm. A heartbeat-dead run is *not* live, so legitimate resumes are never blocked. |
| 5 | `apps/accounts/views_owner_onboarding.py` | Owner progress poll wired to the watchdog (background resume when the in-request kick didn't complete). |
| 6 | `apps/schools/views_pending_provision.py` | Replaced the un-debounced `force=True` re-kick (a thundering herd on `stuck`) with the heartbeat-aware, single-flighted watchdog. |
| 7 | **NEW** `apps/schools/tests/test_provision_watchdog.py` | 7 regression tests (live-untouched, dead-resumed-once, settled-noop, single-flight-debounce, hourly-cap, sweep-resumes, no-FieldError). |

### Deferred (with rationale)
- **Fix D — statement/lock timeout on the migrate.** A `statement_timeout` risks aborting a
  legitimately-slow-but-progressing migration mid-DDL. The safer `lock_timeout` targets only the
  double-migrate lock-hang — which the single-flight guard (#4) already closes — and cannot be
  verified against the Postgres lock path on local SQLite. **Recommended as a staging-verified
  follow-up**, not shipped blind.

---

## 3. Verification (honest)

| Check | Result |
|-------|--------|
| `test_provision_watchdog.py` (7 tests) | ✅ **7 passed** |
| Django `setup()` + both healing jobs register in `periodic.py` | ✅ verified |
| Existing provisioning suite (dispatch, visibility, isolation, e2e) | ✅ passing tests unaffected |
| **Regression check** — the 2 crash-resiliency failures | ⚠️ **pre-existing** — they fail identically with my changes **stashed** (baseline). Cause is a pre-existing `TransactionManagementError` in the provisioning *failure* path, unrelated to this fix. See §4. |
| 3 `SuperProvisioningWizardTests` failures | ⚠️ **pre-existing** — 302 from a host-guard on a bare `RequestFactory` request, and a `QUEUED`-vs-`COMPLETED` event mismatch driven by Celery-eager mode (`super_views_provisioning.py`, unmodified). |
| Harness round-trip (`test_e2e_harness.py`) | Caught a **real teardown bug** (`ProtectedError` on `AcademicYear`/`Department` PROTECT FKs) → fixed with a bounded peel-delete; re-verified. |

**Execution-mode caveat (important):** local verification runs under **SQLite / RLS mode**, which
exercises the whole provisioning pipeline **except** the `tenant_schema` schema migrate (that path
needs Postgres + `USE_DJANGO_TENANTS`). The specific step that hangs in prod is therefore covered
here by the watchdog unit tests and the fault-injection stage, **not** by an end-to-end cold schema
migrate. Run the full matrix on staging Postgres to exercise that step directly (see §5).

---

## 4. Pre-existing issues found (not this fix's regressions — recommended follow-ups)

1. **`TransactionManagementError` in the provisioning failure path** (breaks `test_failure_*`
   crash-resiliency tests on baseline). When `_do_provision_tracked` raises, a query runs inside a
   poisoned atomic block — likely the `finalize_run` → `try_auto_apply_on_failure` recursion or an
   event-log write after rollback. This can prevent a clean FAILED finalize and *contributes to
   stuck states*. Worth fixing (wrap the failure-path writes in fresh savepoints / a new
   connection).
2. **Eager-mode `QUEUED` event** — `test_api_create_school_records_provisioning_events...` expects
   a `QUEUED` event, but eager mode completes synchronously and records `COMPLETED`. Test/env
   mismatch.
3. **Wizard host-guard 302** under bare `RequestFactory` — pre-existing test harness gap.
4. The working tree was already dirty at session start (uncommitted peer changes to
   `apps/payroll/*`, `apps/schoolops/tasks.py`, `apps/accounts/urls.py`, templates, generated
   docs) — unrelated to provisioning.

---

## 5. Test-school lifecycle harness

`python manage.py e2e_lifecycle` — provisions a **country × education-level matrix**, verifies the
lifecycle programmatically, fault-injects the self-heal, writes an honest report, and tears down
**all marker'd test data** with a zero-residue proof.

- **Safety:** every test school carries `zzt-e2e-` slug prefix **AND** `settings["e2e_test"]=True`;
  teardown requires **both** and refuses anything else — a real tenant is unreachable
  (locked by `test_teardown_never_touches_a_real_tenant`).
- **Matrix:** NG / GB / US / IN / GH / AE / FR / KE (distinct currencies, grading scales, locales,
  timezones) + full K-12 and single-level. `--matrix representative` (4) or `full` (8).
- **Run the full schema-per-tenant matrix on staging Postgres:**
  `USE_DJANGO_TENANTS=1 python manage.py e2e_lifecycle --run --matrix full`
- Browser-driven stages (login UI, finance/attendance/portal screens, offline WAL) are **out of
  scope** for this headless harness — run them via the Playwright suite.

---

## 6. Deploy checklist

1. `makemigrations --check` clean (this fix adds **no migrations**).
2. Ensure the web service actually pings `/health/` (it does on Render) so the in-process scheduler
   ticks — that is what drives the new self-heal in the no-beat topology.
3. Optional envs (defaults are safe): `PROVISION_RESUME_STALE_SECONDS` (default 120),
   `PROVISION_RESUME_MAX_PER_HOUR` (default 12).
4. Bump the service-worker `CACHE_VERSION`.
5. Render **Auto-Deploy ON + Manual Deploy + clear build cache**, worker/beat state per your
   topology (the fix does **not** require a worker or beat).
6. After deploy: provision one real school and confirm all 14 steps go green; then simulate a kill
   (or just deploy mid-provision) and confirm the run auto-resumes within ~2 min.

---

## 7. Audit round (2026-07-16) — hardening after 3 adversarial reviews

Three independent adversarial audits (guards, scheduler-wiring, harness+lock_timeout) reviewed
every change. Verdicts: the `/health`-tick wiring **will fire** in the no-beat topology
(`ensure_default_jobs()` runs at startup via `PlatformRuntimeConfig.ready()` AND re-registers on
each tick; `/health` calls `maybe_run_due_jobs()` on all 5 hosts); the teardown is **genuinely
marker-safe**; and the contextvar re-entrancy guard **works on Celery 5.6.3** (eager runs inline,
no `copy_context` — verified from source). Real findings, all fixed:

| Finding | Sev | Fix |
|---|---|---|
| Single-flight cache lock is per-process under `LocMemCache` (Redis-less prod) → double-migrate race not sealed cross-worker | HIGH | **Postgres advisory lock** (`pg_try_advisory_lock`) in `_do_provision` — cross-session; no-op⇒proceed on SQLite; fail-open |
| Re-entrancy guard is a single point of failure for a recursion enabled by default (migration 0086) | HIGH | Kept the contextvar guard **+** `finalize_run(auto_apply=False)` (two independent backstops) + a regression test asserting exactly one drive runs |
| No terminal give-up → operator email storm (~12/hr) on a permanently-broken provision | MED | Email operator **only on first failure** (`_has_prior_failed_provision`), never on auto-resumes |
| One `/health` tick could fan out 10 concurrent migrates on the web dyno | MED | Resume sweep capped to **2/tick** |
| `lock_timeout` could leak onto a pooled connection after an aborted-txn migrate failure | MED | **`connection.close()`** on the migrate-failure path (fresh connect resets all session GUCs) |
| Teardown dropped schema before confirming row-delete; test-user orphans invisible to "zero residue" | LOW-MED | Reordered (drop schema only after row gone); added **user-residue** to the proof; tightened schema-name guard to require the `s_` tenant prefix |
| Pending-poll action-branch had a dead `debounced` token and omitted the real `error` action | LOW | Fixed |

**Deferred (documented, low):** a genuinely hung-but-alive migrate (blocked, process alive) keeps a
fresh heartbeat so the watchdog can't see it — the new `lock_timeout` covers the common
lock-blocked cause; a `statement_timeout` would cover more but risks aborting legitimate slow DDL.

**⚠️ Concurrent editing:** this repo is OneDrive-synced and another session was editing the same
files mid-work (e.g. `finalize_run` gained its `auto_apply` param from a peer). Changes here were
reconciled with, not clobbering, that work — but coordinate to avoid two sessions racing.

## 8. Final validation (2026-07-16)

- **16/16 provisioning tests pass** (`makemigrations --check` → *No changes detected*):
  7 watchdog + 1 recursion-guard + 1 **unstick→fresh-provision demo** + 3 harness (incl. zero-residue
  round-trip) + 4 crash-resiliency (the 2 formerly-failing now green).
- The demo test (`test_unstick_stuck_job_then_fresh_provision_completes`) proves end-to-end:
  detect a heartbeat-dead stuck run → `unstick_provisions` re-drives it + cancels the zombie →
  a brand-new school provisions through the real pipeline to portal-ready, **not stuck**.
- New operator tool: `python manage.py unstick_provisions [--dry-run] [--limit N]` — lists and
  re-drives all stalled/dead provisioning jobs (safe to run against prod; single-flighted per school).
