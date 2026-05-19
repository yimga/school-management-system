# Migration Cloud — per-tenant audit-event rate limiting

> Introduced in v3.40.0 (Agent 14). Lives at
> `apps/migration_cloud/models_audit.py` —
> `AuditEventManager.record()`.

## Threat model

The Migration Cloud audit log (`MigrationCloudAuditEvent`) is
**append-only by design** — rows have `delete()` blocked at the model
level and the manager refuses bulk operations. This is a forensic
property auditors (FERPA, SOC 2 reviewers, tenant operators) rely on:
events written to the chain are durable and tamper-evident.

The flip side: there's no easy way to clean up if an emit site goes
wrong. A runaway loop — either a buggy call site that emits
`migration.guardian_consent.resent` in an `O(N²)` traversal, or a
malicious actor probing an authenticated endpoint that records audit
events — could append millions of rows in minutes. The
`integrity_hash` chain still verifies, but:

- The chain becomes O(million) deep, slowing every subsequent verify.
- Disk fills.
- Genuine events are buried under noise.
- Operator dashboards (Agent 6 Command Center) start showing
  unrealistic counts.

We need a **guard at the write site**, not after the fact.

## Defense

`AuditEventManager.record()` checks a per-`(tenant_id_hash, event_type)`
sliding 1-hour counter **before** writing. The counter is in-memory
(module-level dict + `threading.Lock` — same posture as Agent 12's
alerts module dedupe). On limit hit:

1. ONE `audit.rate_limit_triggered` meta-event is written (capped at
   one per tenant per hour — the meta event itself is **never**
   rate-limited).
2. `AuditEventRateLimitExceeded(tenant_id_hash, event_type,
   count_in_window, limit)` is raised to the caller.

Callers SHOULD catch the typed exception and degrade gracefully (log
the drop, skip the audit emit, continue the request).

### Default limit

```
MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR = 5000
```

5000 events per tenant per event-type per hour is roughly one per
second sustained. Legitimate flows (companion uploads during a school
bulk-onboard, MAA re-sign campaigns) stay well below. Runaway loops
trip it within seconds.

### Tuning guidance

- **Raise** for documented bursty workflows:
  - Mass guardian-consent campaigns (e.g., 8000 students =
    `migration.guardian_consent.minted` × 8000).
  - Domain-wide MAA re-sign drives.
  - Multi-tenant smoke runs hitting many `migration.smoke.*` events.
- **Never lower below 100.** A 100-event-per-hour floor preserves
  margin for legitimate edge cases (10 concurrent token mints + 5
  webhook subscription creations + N companion uploads = quickly above
  any number under ~50).

### Emergency kill switch

```
MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED=1
```

Set this in env when a known-legitimate burst is happening
(e.g., an MAA v2.0 promotion drive across 80 tenants). The rate-limit
becomes a no-op. **Default OFF** — only flip when you've confirmed
the burst is intentional.

## In-memory caveat

The sliding-window counter lives in process memory. Implications:

- **Worker restart resets the window.** A bad emit loop that crashes
  the worker and gets re-spawned by `supervisord` /
  `systemd` / Kubernetes will start counting from zero again.
- **Multi-worker deployments do not share state.** Each Celery /
  Gunicorn worker tracks its own counter. The effective limit is
  `limit × worker_count`.

This is **acceptable**. The rate-limit is a **runaway guard**, not a
hard cap. The honest threat — a tight loop on one box — gets caught;
the contrived adversarial case (one event per worker, distributed
exactly to evade) doesn't materially help an attacker against an
append-only chain.

A future hardening (v3.41+) would put a Redis-backed counter behind
the same `_rate_limit_check_and_increment` shim for cluster-wide
consistency.

## Incident response

### Detecting a runaway

Query the audit table for top event types in the last hour:

```sql
SELECT event_type, COUNT(*)
FROM migration_cloud_migrationcloudauditevent
WHERE created_at > now() - interval '1 hour'
GROUP BY event_type
HAVING COUNT(*) > 1000
ORDER BY COUNT(*) DESC;
```

If a row appears unexpectedly, the rate-limit may already be
suppressing further writes. Confirm by checking for the meta-event:

```sql
SELECT created_at, payload_summary
FROM migration_cloud_migrationcloudauditevent
WHERE event_type = 'audit.rate_limit_triggered'
  AND created_at > now() - interval '1 hour';
```

The meta-event's `payload_summary` shows the (sha256-prefix-only)
tenant, the offending `event_type`, the observed `count_in_window`,
and the active `limit`.

### After identifying the cause

1. Fix the root cause (bug in the emit site, throttle the caller).
2. If you need to absorb a legitimate burst that's coming:
   `MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED=1` until it's done.
3. Restore the kill switch to default OFF.
4. File a record in `docs/MIGRATION_CLOUD_AUDIT_LOG.md` under
   "Rate-limit incidents".

## What this does NOT defend against

- A bulk INSERT via raw SQL bypassing the manager. (The verifier will
  catch any non-canonical row because the integrity_hash will mismatch.)
- An attacker with shell access on the worker. (Bigger problem.)
- A coordinated multi-worker, multi-tenant burst. (Each worker tracks
  its own counter; an attacker who can fire from many boxes evades.)

The defense scope is: **"my own code accidentally fires audit-emit
1M times in a tight loop"**. That's the most likely failure mode and
the one this guard reliably catches.

## Code references

- `apps/migration_cloud/models_audit.py`
  - `AuditEventRateLimitExceeded` (typed exception)
  - `_rate_limit_check_and_increment(tenant_id_hash, event_type)`
  - `_rate_limit_should_emit_meta(tenant_id_hash)`
  - `AuditEventManager.record()` (rate-limit check is the first step
    after sanitization)
- `apps/migration_cloud/tests/test_audit_rate_limit.py`
- `config/settings.py` —
  `MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR`,
  `MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED`
