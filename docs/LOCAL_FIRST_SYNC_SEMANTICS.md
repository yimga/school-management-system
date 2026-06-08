# Local-First Synchronization Semantics

This is the canonical policy for offline conflict handling and CRDT use.

## Core rules

- `apps.sync_engine.policy_registry` owns the versioned entity policy.
- Unknown entities fail closed to protected manual review.
- Grade, finance, identity, permission, message, behavior, and wallet policies
  cannot be weakened by caller overrides.
- Causal LWW uses HLC or Lamport/replica ranks. Raw device wall-clock time is
  not authoritative.
- Grades and money never use generic CRDT registers. Their canonical queues,
  idempotency rules, audit logs, and review workflows remain authoritative.
- Wallet changes remain a unique append-only operation log. Offline overdrafts
  are detected during reconciliation; the platform does not claim they can be
  prevented during a network partition.

## Approved Generic CRDT Namespaces

| Entity | Primitive | Intended use |
| --- | --- | --- |
| `student_note` | HLC LWW | Reversible note draft scalar |
| `lesson_plan` | HLC LWW | Reversible lesson-plan draft scalar |
| `lesson_plan_tags` | OR-set | Concurrent plan tags |
| `telemetry_counter` | G-counter | Non-authoritative monotonic telemetry |

Every CRDT key must start with `<entity>:`. The server binds actor identity to
the authenticated user and submitted device ID, serializes each tenant row with
`select_for_update`, and records `policy_version` in tenant state.
This materialized CRDT state is non-authoritative staging and never writes
canonical attendance, grade, finance, identity, or permission rows. Attendance
continues through its canonical replay handler, which applies the causal policy.

The OR-set retains observed-remove tombstones, so remove-before-add delivery
converges correctly. G-counter operations publish absolute actor-cell values;
component-wise max makes retries idempotent.

## Transport And Bundles

The browser client uses full-width JavaScript integers for HLC milliseconds and
never truncates `Date.now()` to 32 bits. Signed NDJSON delta bundles are
tenant-bound, HMAC-verified, deterministic by JSON key order, policy-versioned,
and validate bundle version and row count.

## Verification

```text
python manage.py verify_sync_semantics
npm run verify:sync-semantics
python manage.py verify_crdt_convergence
```

CRDT convergence means replicas given the same valid operation set reach the
same CRDT state. It does not mean every concurrent human intent is preserved,
and it does not authorize automatic resolution for protected domains.
