# Migration Cloud — data retention purge runbook

Status: SHIPPED with `sms-v3.40.0` (Agent 15).

This document is the operator playbook for the **migration data
retention purge** introduced in v3.40 — the FERPA §99.30
data-minimization counterpart to the audit-event retention purge
shipped by v3.39 Agent 1.

> Read this before running
> `python manage.py purge_completed_migration_bundles --apply`.

## Why this exists

FERPA §99.30 ("Personal information from education records") and its
state-level analogs (NY Ed Law §2-d, IL SOPPA) impose a
**data-minimization obligation**: a data processor must not retain
education records beyond the purposes for which they were obtained.

Migration Cloud receives encrypted bundles via the Companion extension
and writes the ciphertext to `CompanionCiphertextBlob.blob_file`
(default Django storage). After a migration is `complete`, those
ciphertext bytes have served their purpose and SHOULD be purged. The
v3.32 baseline retained them indefinitely; v3.40 closes that gap.

## What is purged vs what is retained

| Item                                | Purged on `--apply`     | Retained         |
| ----------------------------------- | ----------------------- | ---------------- |
| `CompanionCiphertextBlob.blob_file` | YES (storage delete)    | —                |
| `CompanionCiphertextBlob.byte_size` | Zeroed                  | —                |
| `CompanionCiphertextBlob` row PK    | —                       | YES              |
| `ciphertext_sha256` fingerprint     | —                       | YES              |
| `received_at` / `decrypted_at`      | —                       | YES              |
| `CompanionUploadReceipt` row        | —                       | YES              |
| `MigrationAuthorizationAgreement`   | —                       | YES              |
| `MigrationCloudAuditEvent` chain    | —                       | YES (integrity)  |

The audit trail (refs + integrity hashes + metadata) is preserved so
the **integrity-chain verifier** still walks the post-purge state
without gaps; only the actual ciphertext bytes are removed.

## Retention floor + default

| Setting                                   | Default | Purpose                                                       |
| ----------------------------------------- | ------- | ------------------------------------------------------------- |
| `MIGRATION_CLOUD_RETENTION_MIN_DAYS`      | 90      | Hard floor — `--older-than-days < this` is refused.           |
| `MIGRATION_CLOUD_RETENTION_DEFAULT_DAYS`  | 180     | Default cadence the monthly audit task uses.                  |

Rationale for the 90-day floor:

  * K-12 audit cycles routinely look back 60-90 days on disputed
    grades / attendance records.
  * The MAA v2.0 body language commits to "no retention beyond
    migration"; 90 days is the counsel-blessed minimum that still lets
    operators investigate disputes from the migration window.

Rationale for the 180-day default:

  * Most SIS migrations have a 60-day shake-out tail (gradebook
    reconciliation, IEP / 504 plan transfers, transcript audits). The
    180-day default gives 3x headroom.

## Counsel-pending workflow

Mirrors `docs/MIGRATION_CLOUD_AUDIT_LOG.md` § Retention purge
procedure:

1. Counsel reviews the proposed purge cohort (operator runs `--dry-run`
   and shares the candidate-count + byte-total with counsel; the
   dry-run output is PII-free — only counts + sha256 prefixes).
2. Counsel signs off in writing (PDF stored to the operator's secure
   filesystem; URL paste-able into the `--apply` flow if your future
   tooling adds one).
3. Operator obtains the counsel-pending approval token (rotated per
   purge cycle) and provisions
   `MIGRATION_CLOUD_DATA_RETENTION_APPROVAL_TOKEN` in the environment
   for the worker that will run the command.
4. Operator runs `--apply` with `--counsel-token=<token>` and the
   verbatim `--confirm-phrase` `'I AFFIRM MIGRATION DATA RETENTION
   PURGE'`.
5. Operator captures the command's `bundles_purged=...` /
   `bytes_freed=...` line into the post-purge attestation.
6. The command emits a `migration.data_retention.purge_applied` audit
   event so the purge itself is auditable.

## Operator playbook — monthly audit, quarterly purge cycle

Quarterly cadence is the recommended operating point:

  * **Monthly (1st of month, 05:00 UTC)** — Celery beat
    `migration-cloud-retention-audit-monthly` runs the dry-run audit
    task `apps.migration_cloud.tasks_retention.purge_completed_migration_bundles_audit_task`.
    The task emits a `severity="info"` alert per tenant with non-zero
    candidates so operators see the running backlog without on-call
    pages.
  * **Quarterly** — operators batch up the eligible cohorts, obtain
    counsel signoff, and run `--apply` once per tenant per quarter.

## CLI reference

```
python manage.py purge_completed_migration_bundles \
    --tenant <slug>                         # required
    --older-than-days <N>                   # required; floor 90
    --counsel-token <token>                 # required for --apply
    --confirm-phrase 'I AFFIRM MIGRATION DATA RETENTION PURGE'  # required for --apply
    --apply                                 # default OFF (dry-run)
```

Exit codes:

  * `0` — dry-run or apply succeeded.
  * `1` — refused (no counsel approval, token mismatch, phrase
    mismatch, or below-floor `--older-than-days`).

## Never-log assertions

The command MUST NOT log:

  * Raw counsel approval token (constant-time-compared only)
  * Raw tenant slug (sha256-prefix only)
  * Raw bundle PKs (sha256-prefix only, when logged at all)
  * Blob file paths (best-effort delete is wrapped; failures emit
    only sha256-prefixed identifiers)
  * Blob ciphertext bytes (never read off disk)

Test coverage in `apps/migration_cloud/tests/test_retention_purge.py`
asserts the audit-event payload is PII-free and tenant isolation
holds.

## Honest-deferred (v3.41+)

  * Bundle ↔ intake direct FK: today the command's Tier-1 path uses
    `MigrationIntakeRequest.state == "complete"` only as a sanity
    check; the actual identification falls back to
    `decrypted_at IS NOT NULL`. A direct FK from
    `CompanionCiphertextBlob → MigrationBundle → MigrationIntakeRequest`
    would let Tier 1 fire instead of Tier 2. The v3.40 ship is
    intentionally conservative because the Tier-2 predicate already
    catches every truly-completed bundle.
  * Plaintext-bundle purge: if a future feature ever persists the
    decrypted bundle alongside the ciphertext (it does not today),
    this command MUST also purge those bytes. Update both sides of
    the table above when that change lands.
  * Per-tenant retention overrides: today every tenant honours the
    same `MIGRATION_CLOUD_RETENTION_DEFAULT_DAYS`. A future
    enterprise-tier feature could let a tenant configure a longer
    retention window via SiteSettings; the floor must still apply.
