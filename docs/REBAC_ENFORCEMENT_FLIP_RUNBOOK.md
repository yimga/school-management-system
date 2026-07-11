# ReBAC sensitive-resource enforcement — flip runbook

Operator procedure for enabling `RMC_REBAC_ENFORCE_SENSITIVE`. This is the one
authorization change that is deliberately gated on a live pre-flight rather than
shipped default-on, because a premature flip can deny legitimately-permissioned
users. Read the whole runbook before starting; the flip is reversible in seconds.

## What the flip does

`enforce_permission_token(user, code, school)` (`apps/accounts/rebac.py`) gates
the sensitive capability codes below. Its logic is a strict **AND**:

```
RBAC allows?  ── no ──▶ deny         (RBAC is always the first gate)
    │ yes
    ▼
RMC_REBAC_ENFORCE_SENSITIVE off? ── yes ──▶ allow   (shadow mode: RBAC alone)
    │ off→on
    ▼
`can` tuple exists?  ── no ──▶ deny + log `rebac_enforce_denied`
    │ yes
    ▼
  allow
```

Because it is an AND, enabling enforcement can only ever **tighten** access — it
can never grant a code that RBAC denied. The only failure mode is a *false*
denial: a user RBAC allows but whose ReBAC `can` tuple is missing or stale.

### Why a false denial is possible at all

`User.has_feature_permission` grants a code only via superuser, a direct
`feature_permissions` row, a role-permission row, or a temporary grant.
`rebuild_user_permission_tuples` writes a `can` tuple for exactly those same
sources, school-scoped identically, and `apps/accounts/rebac_signals.py`
re-syncs on every membership / role / permission / grant mutation. So parity is
**structural** — there is no admin-tier bypass gap. The residual risk is purely
**operational drift**: a tenant whose tuples were never backfilled, a signal
that failed silently, or a bulk import that bypassed the signals.

### Enforced codes (the sensitive surface)

`apps/accounts/rebac_readiness.py::SENSITIVE_ENFORCED_CODES` is the source of
truth. Today:

| Code | Wired at |
|---|---|
| `finance.view` | `apps/finance/api_views.py` (`RebacPermission`) |
| `finance.manage` | `apps/finance/api_views.py`, `apps/api/mobile_api.py` (offline payment sync) |
| `grade.submit` | `apps/api/mobile_api.py` (offline grade/eval sync) |
| `attendance.mark` | `apps/api/mobile_api.py` (offline attendance sync) |

When a new surface adopts enforcement, add its code here so the pre-flight covers it.

## The flip is GLOBAL

`RMC_REBAC_ENFORCE_SENSITIVE` is a single environment variable — it enables
enforcement for **all tenants at once**. Therefore **every** tenant must be ready
before you flip. The pre-flight command below enforces exactly that: with no
`--school-id` it checks all active schools and exits non-zero if *any* tenant has
drift.

## Procedure

### 1. Backfill tuples for all tenants

```
python manage.py sync_rebac_tuples
```

Writes/refreshes the `can` tuples from the live membership / guardian /
teacher-assignment / role / direct-permission / temporary-grant graph. Idempotent
— safe to re-run.

### 2. Pre-flight: prove parity (the go/no-go)

```
python manage.py check_rebac_enforcement_readiness
```

- **Exit 0 / `PASSED`** → every active member holding a sensitive code has the
  matching tuple. Safe to proceed.
- **Exit 1 / `NOT-READY`** → prints each tenant plus every `would-deny
  user_id=… code=…`. These are the exact users who would be locked out. Do **not**
  flip. Go back to step 1 (or investigate why a signal didn't fire for that
  user), then re-run until green.

Scope to one tenant while investigating with `--school-id <pk>`.

### 3. (Recommended) corroborate with the shadow logs

Dual-run logging (`RMC_REBAC_DUAL_RUN_LOG_MISMATCH`, default on) already emits
`rebac_rbac_mismatch` whenever RBAC and ReBAC disagree in production. Over a soak
window, zero mismatches on the enforced codes is an independent confirmation of
the pre-flight. The pre-flight is the *active* proof; the logs are the *passive*
cross-check.

### 4. Flip

Set the environment variable and redeploy / restart:

```
RMC_REBAC_ENFORCE_SENSITIVE=1
```

### 5. Monitor

Watch application logs for:

```
rebac_enforce_denied user_id=… school_id=… code=… (rbac=allow rebac=deny — missing/stale can tuple)
```

Any occurrence is a user who reached the enforce path with a missing tuple — a
drift that appeared *after* the pre-flight (e.g. a tenant onboarded or a bulk
import run between step 2 and the flip). It is instantly diagnosable from the log
line. Heal it without a rollback by re-running `sync_rebac_tuples` (or
`sync_rebac_tuples --school-id <pk>`); the signals will keep it fresh afterward.

### 6. Rollback (seconds, no data change)

```
RMC_REBAC_ENFORCE_SENSITIVE=0    # or unset
```

Redeploy / restart → instant revert to shadow mode (RBAC-only). No migration, no
data mutation; the tuples remain in place, so there is nothing to undo and
re-flipping later is immediate.

## Guarantees / non-goals

- **Cannot escalate:** enforcement is an AND on top of RBAC, so the flip can
  never grant access RBAC denied.
- **Worst case is a false denial**, which the pre-flight prevents and the
  `rebac_enforce_denied` log diagnoses.
- **Not a per-tenant rollout:** the flag is global. Per-tenant staging would
  require promoting the flag to a tenant setting — out of scope until requested.
- **Superusers are never affected** (both RBAC and ReBAC short-circuit to allow).

## Related code

- `apps/accounts/rebac.py` — `enforce_permission_token`, `check_permission_token`
- `apps/accounts/rebac_readiness.py` — `enforcement_readiness`, `SENSITIVE_ENFORCED_CODES`
- `apps/accounts/management/commands/check_rebac_enforcement_readiness.py`
- `apps/accounts/management/commands/sync_rebac_tuples.py`
- `apps/accounts/rebac_signals.py` — the auto-resync handlers
- `apps/accounts/tests/test_rebac_enforcement_readiness.py` — parity/drift/heal proof
