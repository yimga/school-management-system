# apps/lifecycle

> The tenant's life story: draft → provisioning → live → wind-down → closed →
> purged, plus the signed DR snapshots and the signed deletion certificate.

**Tenancy:** SHARED (public schema; rows carry an explicit `school` reference or a plain school id, not a Postgres schema)
**Scale:** 3 models · 5 migrations · 11 test modules · ~8.7k LOC

## What this app owns

Lifecycle answers "what state is this tenant in, and what is the control plane
allowed to do to it right now?" It owns the canonical phase contract
(`draft → provisioning → activating → live → wind_down → closed → purged`), the
readiness score that says how close a new school is to launch, the wind-down guards
that stop commerce on a dying tenant, the resumable purge state machine with its
HMAC-signed deletion certificate, and the daily encrypted DR snapshot.

The defining decision is that `unified_lifecycle.py` is a **facade, not a
replacement**. Lifecycle state already lived in four places — School flags,
provisioning events, the lifecycle spine, and the offboarding JSON blob — and this
module maps them into one read/write surface rather than migrating them into a new
table. That is why an app with ~8.7k LOC declares only 3 models.

The second decision is that the records which prove a deletion must **outlive the
thing they describe**. `PurgeOperation` stores `school_id`/`school_slug` as plain
fields with **no FK**, so the row survives the School being dropped and stays
idempotent afterward. A purge certificate you cannot produce after the purge is
worthless.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `SchoolLifecycleStage` | `lifecycle_schoollifecyclestage` | One recorded stage transition for a school — the spine `unified_lifecycle` reads and writes |
| `PurgeOperation` | `lifecycle_purgeoperation` | Resumable purge state machine. `completed_phases` lets a re-run skip finished work; **no FK to School by design** so it survives the tenant; carries the HMAC-signed deletion certificate |
| `TenantImmutableSnapshot` | `lifecycle_tenantimmutablesnapshot` | One row per school per UTC snapshot day — metadata + `payload_sha256` + primary/secondary store URIs for the DR blob |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `capture_tenant_immutable_snapshots_daily` | Daily DR snapshot capture (`tasks_dr_snapshot.py`) |
| Celery task | `verify_tenant_snapshot_restore_integrity` | Restore-integrity verification |
| Module | `tenant_dr_snapshot` | Compile / encrypt / sign / restore (see below) |
| Module | `unified_lifecycle` | The phase facade — call this, not the underlying stores |
| Module | `wind_down` + `wind_down_guards` | `is_wind_down_mode(school)` + decorators blocking finance/roster writes |
| Module | `purge_operations` + `purge_certificate` | Resumable purge FSM + HMAC-SHA512 signed certificate |
| Module | `readiness` | Merges the two competing progress scores into one 0-100 number |
| Module | `billing_gate` | `check_billing_clearance(school)` — returns `unknown` (not "blocked") when finance state is unresolvable |
| Module | `services_clone` | Clone-from-template school; clones brand/locale/settings, **never** id/slug/subdomain or active/approved flags |
| Module | `services_offboarding` | Soft-delete + grace window + DSAR + audit-chain mirror |
| Module | `tasks_stall_watch` | Stall detection — **deliberately not auto-registered** in Celery beat; the wiring snippet is in its docstring |
| URLs | `timeline` | This app registers one URL name; its other views are reached through control-plane surfaces |

## Before you change this

- **DR snapshots are encrypt-then-MAC, and the encryption is load-bearing PII
  protection — not belt-and-braces.** The payload carries the tenant's whole config
  core: student/teacher PII, the finance ledger, and `accounts.User` rows whose
  **password hashes are captured verbatim** (so a DR restore keeps credentials).
  Left as plain gzip — which is what it was — anyone who could read
  `var/tenant_snapshots/` or the `TENANT_SNAPSHOT_S3_BUCKET` could `gzip.decompress`
  the lot. Blobs are now Fernet ciphertext at rest in every store.
- **The signature covers the CIPHERTEXT, and is verified BEFORE decrypting.**
  `restore_from_snapshot` fails closed on tamper before opening a transaction or
  writing a row. Do not reorder this to decrypt-then-verify.
- **The confidentiality key and the integrity key are different bytes.** Both derive
  from `SECRET_KEY` + school id, but under distinct domain-separation labels
  (`:tenant-snapshot:` vs `:tenant-snapshot-encryption:`). Reusing one key for both
  HMAC and encryption is a classic footgun — keep them separated.
- **The legacy gzip passthrough is not a downgrade vector.** `decrypt_blob` passes a
  blob starting with gzip magic (`\x1f\x8b`) through unchanged so pre-encryption
  backups stay restorable — a DR system that cannot read its own history is worse
  than one that was late to encrypt. It is safe *only because* the HMAC over the
  stored bytes is verified first and cannot be forged without `SECRET_KEY`. If you
  ever move verification after this call, the passthrough becomes a real hole.
- **The restore plan is strictly FK-dependency ordered** (School → User →
  ComplianceProfile → AcademicYear → Department → Term → Classroom → StudentProfile →
  TeacherProfile → Invoice → InvoiceLine → Payment). `InvoiceLine` is deliberately
  restored *before* `Payment` so the invoice total is real when the payment recalc
  fires. Reordering silently corrupts balances.
- **Snapshot schema 2.1 is a pure superset of 2.0** — it only ADDS table keys, so old
  blobs restore unchanged (new specs find no rows and no-op). Keep additions additive.
- **`PurgeOperation` must never gain an FK to School.** That is the whole point.
- `billing_gate` returns `unknown` rather than blocking when it cannot resolve finance
  state, so dev environments without billing wired do not deadlock purges — operators
  override via dual approval. Do not "fix" this into a hard block.
- `tasks_stall_watch` is best-effort observability and must never crash the worker.
