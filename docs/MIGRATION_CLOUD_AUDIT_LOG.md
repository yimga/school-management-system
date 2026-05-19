# Migration Cloud audit log

**Status:** base append-only audit log shipped in v3.38.0 Agent 5; v3.39.0 added weekly verification, counsel-gated purge, and root-key signature hardening (2026-05-19).
**Owner:** Migration Cloud platform team.
**Companion docs:** `docs/SECURITY_KEYS.md` (key types, rotation),
`docs/DPA_TEMPLATE.md` (GDPR Art. 28), `docs/DSAR_RUNBOOK.md` (data
subject access).

**V3.40 boundary (Agent 5 ledger, 2026-05-19):** this document is evidence for the v3.38/v3.39 audit-log hardening, not proof that the legacy webhook header family has been removed. The header-family cutover is governed by `docs/WEBHOOK_HEADER_MIGRATION_2026.md` and remains future-dated until after **2026-08-18**; do not claim v3.40 legacy-header removal from this audit-log document.

## What this is

`MigrationCloudAuditEvent` is a tamper-evident, append-only audit
log for every sensitive Migration Cloud event. Each row carries a
SHA-256 integrity hash that chains to the previous event's hash for
the same tenant; tampering breaks the chain and is detected by
`python manage.py verify_audit_chain --tenant=<slug>`.

External auditors (FERPA / SOC2 reviewers; tenant operators with
DSAR requests) consume the log through the JSONL export endpoint at
`/super/migration/audit/export/`. The auditor receives the hashed
identifiers (tenant_id_hash, actor_id, event_subject_hash); the
RunMyCampus operator maintains a separately-stored map outside this
app for forensic correlation.

## Schema

Defined in `apps/migration_cloud/models_audit.py`. Migration:
`apps/migration_cloud/migrations/0020_migration_cloud_audit_event.py`
(pure `CreateModel` + `AddIndex`; no `RunPython`).

| Field | Type | Notes |
|---|---|---|
| `id` | UUIDv4 | PK, random, NEVER auto-increment (would leak volume) |
| `tenant_id_hash` | char(12) | First 12 hex chars of `sha256(tenant_slug)` |
| `event_type` | char(64) | One of the `MigrationCloudAuditEventType` choices |
| `actor_id` | char(64) nullable | `sha256(user.email)[:64]` or NULL for system events |
| `event_subject_hash` | char(64) nullable | `sha256(subject)[:64]` or NULL |
| `payload_summary` | JSONField | Walked by `_sanitize_payload` — sensitive keys REJECTED |
| `created_at` | datetime | `auto_now_add` |
| `created_at_iso` | char(32) | ISO-8601 UTC; present even on raw-SQL exports |
| `integrity_hash` | char(64) | SHA-256 of canonical-JSON pre-image |
| `prev_event_hash` | char(64) | Previous event's `integrity_hash` per tenant, or `"genesis"` |

Indexes: `(tenant_id_hash, created_at)`, `(event_type, created_at)`.
**No unique constraints** — chain integrity is verified externally.

## Event types

Registered via `MigrationCloudAuditEventType` TextChoices:

- `companion.upload` — Companion-extension upload accepted.
- `maa.sign` — MAA bound.
- `maa.sign_attempt_draft` — Attempt to sign a DRAFT version refused.
- `key.rotate` — Per-tenant companion X25519 keypair rotated.
- `webhook.subscription.created` — Operator created an outbound subscription.
- `webhook.subscription.deleted` — Operator deactivated a subscription.
- `webhook.delivery.replay` — Operator manually replayed a delivery.
- `token.mint` — Operator minted a scoped API token.
- `token.revoke` — Operator revoked a scoped API token.
- `legacy_hash.decrypt` — Legacy SIS-hash field decrypted at first login.

## Append-only contract

Three layers enforce immutability:

1. **`save()` override** — refuses to mutate an existing row by
   raising `MigrationCloudAuditEventReadOnlyError` if `self.pk` is
   set and a row with that pk exists.
2. **`delete()` override** — always raises
   `MigrationCloudAuditEventReadOnlyError`.
3. **`AuditEventManager`** — inherits from `AppendOnlyManager` which
   refuses `QuerySet.delete()`.

The only documented mutation path is the `verify_audit_chain
--repair-genesis` command, which uses raw SQL to populate a missing
`prev_event_hash` on the first event per tenant. It NEVER modifies
later events. The repair is logged.

## Hash chain semantics

Canonical pre-image (sorted keys, no whitespace, `ensure_ascii=False`):

```json
{
  "id": "<uuid-hex>",
  "tenant_id_hash": "<12-hex>",
  "event_type": "<name>",
  "actor_id": "<64-hex-or-null>",
  "event_subject_hash": "<64-hex-or-null>",
  "payload_summary": {<dict>},
  "created_at_iso": "<iso-8601-utc>",
  "prev_event_hash": "<64-hex-or-genesis>"
}
```

`integrity_hash = sha256(canonical_json)`. The very first event per
tenant uses `prev_event_hash = "genesis"`.

Re-derivation is in `recompute_integrity_hash()`; chain comparison
uses `hmac.compare_digest` everywhere.

## Operator workflow

### Browse: `/super/migration/audit/`

Staff-only Django view. Displays the last 200 events filterable by
`event_type`, `date_from`, `date_to`, `tenant` (12-hex prefix).
Hash columns are truncated to 12 chars in the UI. Payload column is
re-sanitized via `_sanitize_payload` before render (defense in
depth).

### Export: `/super/migration/audit/export/`

Staff-only. Streams `application/x-ndjson` (JSONL). Query params:

- `?tenant=<hash>` — 1-12 hex char prefix.
- `?from=<iso-or-date>` — lower bound on `created_at`.
- `?to=<iso-or-date>` — upper bound on `created_at`.
- `?verify_chain=1` — adds `_chain_verified: true|false` per line.

Pages 100 rows at a time via `StreamingHttpResponse`; memory bounded.

### Verify: `manage.py verify_audit_chain`

```
$ python manage.py verify_audit_chain --tenant=ghs-limbe
verify_audit_chain: clean tenant='ghs-limbe' events=12345
$ echo $?
0
```

Exit 1 on broken chains, with broken event IDs printed to stderr.

## Retention

Audit events are retained for **7 years** per FERPA + per-state Ed-law
minimums. NY Ed Law §2-d and CCPA §1798.100 both reference longer
windows for certain record types; consult counsel before purging.

Purge mechanics are NOT yet implemented — append-only is real, so
purge must use a counsel-approved one-shot management command that
documents the row range purged. See deferred docket below.

## Counsel notes for external auditors

- **Hashed actor_id.** Auditors see SHA-256-prefix hashes only. To
  correlate "which user did this?" the RunMyCampus operator
  maintains a separately-stored email→hash map OUT of this app
  (typical home: a sealed forensic spreadsheet kept in operator-only
  cloud storage). The operator releases mappings to counsel under
  the DSAR / subpoena process documented in `docs/DSAR_RUNBOOK.md`.
- **No raw PII or secret material is stored.** The
  `_sanitize_payload` helper rejects any payload key matching the
  sensitive-keyword regex (`password`, `passwd`, `pwd`, `hash`,
  `secret`, `token`, `ssn`, `dob`, `api_key`, `apikey`,
  `private_key`, `signature_text`, `email`, `slug`). Slug is on the
  list deliberately — only the `tenant_id_hash` prefix is allowed
  in the audit log; the raw slug stays out.
- **Chain breakage is alertable.** Operators are expected to run
  `verify_audit_chain` as a weekly cron beat; this is queued for
  v3.39+ (see deferred docket).

## Weekly verifier beat (v3.39.0)

A Celery beat entry `accounts-verify-audit-chain` runs every Monday
at **02:00 UTC** (`crontab(hour=2, minute=0, day_of_week="mon")`).
The entry is lazy-guarded behind `_celery_crontab`; a CI lane without
celery installed falls back to a 7-day interval.

### Task body

The task lives at
`apps/migration_cloud/tasks_audit.py::verify_audit_chain_weekly_task`.
It wraps:

```
python manage.py verify_audit_chain --all-tenants \
    --email-on-broken=$MIGRATION_CLOUD_AUDIT_OPS_EMAIL
```

inside a `try/except` that:

- logs ERROR on any verifier exception but NEVER propagates,
- treats the verifier's `sys.exit(1)` (broken chain) as a normal
  outcome (the broken-chain email has already gone out),
- logs WARNING + skips the email arm when
  `settings.MIGRATION_CLOUD_AUDIT_OPS_EMAIL` is unset / empty.

### Email contract

When **at least one tenant chain is broken**, the verifier sends a
single email via `django.core.mail.send_mail` to
`MIGRATION_CLOUD_AUDIT_OPS_EMAIL`. The body contains ONLY:

- `tenants_checked`, `tenants_broken`, `total_events_checked` counters,
- a per-tenant break summary table: `tenant_id_hash` (12-hex prefix)
  · `broken_count` · `first_broken_event_uuid`,
- pointers to `manage.py verify_audit_chain --tenant=<slug>` and to
  this document.

The body is engineered so it NEVER carries:

- raw `integrity_hash` bytes,
- raw `payload_summary` content,
- raw tenant slugs,
- raw `actor_id` / `event_subject_hash` bytes.

Tenant-hash → slug correlation lives OUTSIDE this app (see "Counsel
notes" above).

### Reading the break report

When the email lands, the on-call operator runs:

```
$ python manage.py verify_audit_chain --tenant=<slug>
```

for the corresponding slug (resolved via the operator-only correlation
map). The single-tenant verifier prints broken event UUIDs to stderr.
If the first event has a missing `prev_event_hash` (rare — usually
indicates a partial DB restore), `--repair-genesis` populates the
sentinel; later events MUST NOT be touched without counsel signoff.

## Retention purge procedure (counsel-pending until token provisioned)

The append-only contract is real — there is no `delete()` path through
the Django ORM. The ONLY documented path that removes audit rows is
the management command:

```
python manage.py purge_audit_events_pre_approved \
    --tenant=<slug> --before=<iso-date> \
    --counsel-approval-token=<token> [--apply]
```

### Counsel signoff PDF

A retention purge MUST be backed by a counsel signoff PDF stored under
`docs/legal/audit_retention_signoff_<YYYY-MM-DD>.pdf` (operator-only).
The PDF documents:

- the regulatory basis (FERPA / GDPR / state Ed-law minimum retention),
- the cutoff date,
- the affected tenant slugs (mapped via the operator-only correlation map),
- expected row range (count, first/last UUID),
- explicit counsel authorization.

The PDF is referenced by the operator runbook entry that follows the
purge — the PDF itself is not stored in this repo.

### Token-provisioning flow

The command guards on `settings.MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN`
(env var `MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN`). The default is
**empty string**; with an empty setting the command prints
"Counsel approval pending — see docs/MIGRATION_CLOUD_AUDIT_LOG.md
§ Retention" and exits **1** regardless of the supplied flag value.

Operators provision the env var AFTER the counsel PDF is on file,
rotate it OUT after each purge cycle, and treat the token like any
other secret (do NOT check into version control; do NOT log).

The token compare uses `hmac.compare_digest` so timing does not leak
whether the setting is set or whether the supplied value is correct.

### Dry-run-first contract

`--apply` is required to perform the DELETE. Without it the command:

- counts rows in the eligible window,
- prints the first/last event UUID prefixes (8-char) and total count,
- prints the warning "this operation is irreversible and violates
  the append-only contract — proceed only with counsel signoff PDF
  on file",
- exits 0 without touching any row.

The operator MUST run dry-run first, sanity-check the count against
the counsel-approved window, then re-run with `--apply`.

### Irreversibility

`--apply` uses **raw SQL** (`DELETE FROM migration_cloud_migrationcloudauditevent
WHERE tenant_id_hash=%s AND created_at < %s`) — bypassing the
append-only `delete()` guard intentionally. The DELETE is wrapped in
`transaction.atomic()` so a partial purge cannot leave the chain in a
mixed state.

There is no undo. Past the `--apply` invocation, the rows are gone
from the row store. (If the operator-only backup retains a pre-purge
dump, recovery is possible by restoring from backup; this is operator
discretion, not an in-app feature.)

### Meta-audit-event emitted by the purge itself

Even though raw SQL was used to delete the rows, the purge writes a
meta-event INTO the same audit table via
`AuditEventManager.record()`. The meta-event:

- type: `audit.retention_purge_applied`
- `payload_summary`:
  - `tenant_prefix` — first 6 hex chars of the tenant_id_hash,
  - `rows_purged` — integer row count,
  - `cutoff_iso` — the parsed `--before` cutoff as ISO-8601,
  - `approval_fingerprint` — first 12 hex chars of
    `sha256(settings.MIGRATION_CLOUD_AUDIT_PURGE_APPROVAL_TOKEN)`,
    so the token bytes are NEVER stored.

The meta-event is itself append-only — the next time
`verify_audit_chain` runs it sees the meta-event AND verifies its
integrity hash matches. A subsequent compromise that retroactively
edits or deletes the meta-event will be detected on the next sweep.

The meta-event becomes the new chain head for the purged tenant.

## Root-key signature (v3.39.0)

### What it adds

The append-only chain (`integrity_hash` + `prev_event_hash`) defends
the audit log against attackers who can WRITE to the database — they
cannot insert a new row without breaking the next row's link. It does
NOT defend against an attacker who can REPLACE the entire row store
from a tampered backup: every row's `integrity_hash` and
`prev_event_hash` is recomputable purely from data the attacker now
controls.

`MigrationCloudAuditEvent.root_key_signature` closes that gap. The
field stores an HMAC-SHA512 digest (128 hex chars) over the SAME
canonical-JSON pre-image that `integrity_hash` covers, keyed by a
secret that lives OUTSIDE the database (env var or — future — HSM).
An attacker who restores from a tampered backup CANNOT regenerate the
signatures unless they also exfiltrated the signing key. SHA-512 is
used (not SHA-256) so a single-algorithm compromise cannot collapse
both checks.

### Key configuration

1. Generate 32 random bytes; base64-encode the result:

   ```
   python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
   ```

2. Provision it in the same secret manager that holds
   `DJANGO_CRYPTOGRAPHY_KEYS` — but on a DIFFERENT IAM principal /
   rotation boundary (so a compromise of either does not yield the
   other). See `docs/SECURITY_KEYS.md` § "Audit-event root-key
   signature".

3. Expose it to the Django process as
   `MIGRATION_CLOUD_AUDIT_SIGNING_KEY`. `settings.py` reads:

   ```
   MIGRATION_CLOUD_AUDIT_SIGNING_KEY = os.environ.get(
       "MIGRATION_CLOUD_AUDIT_SIGNING_KEY", ""
   )
   ```

   NEVER commit a literal key value to the repo.

4. Restart the Django + Celery workers. From now on every new audit
   event lands with `root_key_signature` populated. Events written
   before the key was provisioned remain with
   `root_key_signature=NULL` ("unsigned legacy") — distinct from
   "signature mismatch".

### HSM pluggability (reserved)

`MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND` selects the signing surface:

| Value | Status | Notes |
|---|---|---|
| `local-env-key` | shipped (default) | HMAC computed in-process with the env-loaded key |
| `aws-kms` | reserved | Configure HSM bridge first; raises `NotImplementedError` |
| `azure-keyvault` | reserved | Configure HSM bridge first; raises `NotImplementedError` |
| `hashicorp-vault` | reserved | Configure HSM bridge first; raises `NotImplementedError` |
| `gcp-kms` | reserved | Configure HSM bridge first; raises `NotImplementedError` |

The audit-event writer honestly refuses to silently degrade when an
HSM-reserved backend is selected without a bridge: `NotImplementedError`
propagates rather than the row landing unsigned. Operators who set
the backend value MUST also implement the bridge in
`apps/migration_cloud/services/audit_root_signing.py` (single point of
extension — `_resolve_signing_key`).

### Legacy-event handling

Events written before the operator provisioned a signing key carry
`root_key_signature=NULL`. The verifier reports them as
**unsigned legacy** — explicitly distinct from "signature mismatch":

- **chain ok, all signatures verify** → exit 0
- **chain ok, some signatures NULL** → exit 0 with
  `unsigned_legacy=<count>` note
- **chain ok, some signatures MISMATCH** → exit **2** (NOT 1) —
  this is the backup-restore tamper signal
- **chain broken** → exit 1 (chain breakage takes precedence)

The exit-code split lets the weekly Celery beat distinguish "the
DB was restored from a tampered backup" from "an attacker inserted
rows directly" — both are alertable, but they imply different
incident-response paths.

### Verification

#### CLI

```
python manage.py verify_audit_chain --tenant=<slug> --check-root-signature
python manage.py verify_audit_chain --all-tenants --check-root-signature
```

#### Export-line verification

The JSONL export view at `/super/migration/audit/export/` honors
`?verify_root_signature=1` in addition to `?verify_chain=1`. Each
line gains `_root_signature_verified: true|false|null` (the `null`
case is "unsigned legacy"). Auditors who hold the signing key can
re-verify the export offline against the same canonical-JSON
pre-image documented above.

#### Programmatic

```
from apps.migration_cloud.services.audit_root_signing import (
    compute_root_signature, verify_root_signature,
)

result = verify_root_signature(event)
# True  — signature present and matches
# False — signature present and does NOT match (TAMPER signal)
# None  — signature absent (legacy event)
```

## Deferred / external gates (v3.40+ boundary)

- Real signed Tauri / Docker release artifacts still require external
  signing material, GitHub Actions secrets, and release tag execution.
  The v3.39 procedure and preflight script exist, but no artifact is
  certified by this audit-log doc.
- HSM bridge implementation for at least one of the four reserved
  backends (`aws-kms` / `azure-keyvault` / `hashicorp-vault` /
  `gcp-kms`) — currently each raises `NotImplementedError` with a
  "configure HSM bridge first" message.
- Legacy `X-Migration-Cloud-*` webhook header removal remains a
  customer-cutover milestone after **2026-08-18**. Until that date and
  operator confirmation, the evidence remains dual-emit / migration
  readiness, not removal.

### Closed since the earlier deferred docket

- Canonical-header drift locking now exists as
  `scripts/scan_companion_canonical_headers_drift.py`; Agent 5
  re-ran it on 2026-05-19 with **0 unallowed drift**.
- Signed-release procedure/preflight now exists in
  `docs/COMPANION_SIBLINGS_SIGNED_RELEASE.md` and
  `scripts/preflight_signed_release.py`; Agent 5 re-ran the stdlib
  tests on 2026-05-19 and got **18/18 OK** across signed-release and
  canonical-header scanner tests.
