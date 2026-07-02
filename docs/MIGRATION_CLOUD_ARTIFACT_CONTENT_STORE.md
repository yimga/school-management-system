# Migration Cloud — per-artifact content store (Phase U5)

_Shipped 2026-07-02 (gap #2). Commit `38957c79b`._

## The problem it closes

`BundleIngestionService.ingest` (`apps/migration_cloud/services.py`) created each
`MigrationArtifact` with **metadata only** — path / filename / sha256 / byte_size /
encoding — and dropped `ArtifactPayload.content_opener`, the lazy stream callable
that is the *only* handle to an artifact's source bytes. That callable cannot
survive the ingest → profile process boundary.

As a result, the profiler (Phase U2) and the apply orchestrator (Phase U5) could
only read bytes for the **single top-level local file** at
`bundle.intake_source_uri` (where `path_within_bundle == path.name`). Every other
shape:

* **archive members** (`parent_archive_id` set), and
* **multi-file / remote / OAuth-folder pulls** (API pull, OAuth Drive, database,
  SQL dump, PDF, Access) whose bytes are not a single local file

profiled **schema-only** and applied **zero rows, silently**.

## The design

Capture each artifact's source bytes **at ingest**, while `content_opener` is
still valid, into a separate encrypted 1:1 table; read them back downstream.

### Model — `MigrationArtifactBlob` (`apps/migration_cloud/models.py`)

| field | type | note |
|---|---|---|
| `artifact` | `OneToOneField(MigrationArtifact, related_name="blob")` | cascade |
| `payload` | `EncryptedBinaryField` | Fernet ciphertext; decrypts on read |
| `byte_size` | `BigIntegerField` | plaintext length; metrics/integrity |
| `sha256` | `CharField(64)` | re-verified on every read |
| `created_at` | `DateTimeField(auto_now_add)` | |
| `expires_at` | `DateTimeField(db_index)` | PII-minimisation clock |

`payload` reuses the shared `EncryptedBinaryField` (`apps/accounts/legacy_hashes/
encryption.py`) — same Fernet key + rotation as the connector secret, webhook
secret, and companion keypair. It deconstructs to `django.db.models.BinaryField`,
so the DB column is a plain BLOB / bytea and `makemigrations --check` stays clean.
Migration: `0033_migration_artifact_blob.py` (pure CreateModel + one index; no data
migration — existing bundles keep the single-local-file fallback).

### Service — `apps/migration_cloud/artifact_blob_store.py`

The single home for crypto / settings / lifecycle, so every wiring site is a
one-liner:

* `capture_artifact_blob(artifact, payload)` — best-effort, never raises. Called
  right after the artifact row is created at ingest.
* `open_artifact_blob_stream(artifact) -> (BytesIO | None, encoding)` — blob-first
  read; re-verifies sha256 and returns `(None, "")` on mismatch so the caller
  falls back to its own path logic. **Reads are unconditional** (not gated on the
  enable flag) so toggling the flag off never breaks in-flight bundles.
* `purge_expired_artifact_blobs()` — the daily sweep.
* `delete_blobs_for_bundle(bundle)` — the drop-on-reconcile hook.

### Wiring (additive, blob-first)

| site | change |
|---|---|
| `services.py::ingest` | one `capture_artifact_blob(...)` call after each create |
| `profiler.py::_resolve_stream` | try blob first, then the legacy path |
| `orchestrator.py::_iter_canonical_rows` | try blob first, then the legacy path (the three row iterators were split into `path` + `stream/text` cores so both feed identical parsing) |
| `reconciliation.py` | drop the bundle's blobs when it reaches `RECONCILED` |
| `platform_runtime/periodic.py` | daily `migration_cloud.purge_expired_artifact_blobs` job |

Single-file bundles behave exactly as before; archive / remote artifacts now
resolve.

## Security posture

The bytes are student PII (rosters, grades, guardian contacts, health / behaviour
records). The store is:

* **Encrypted at rest** — Fernet AES-128-CBC + HMAC via the shared shim. The raw
  column is a Fernet token (`gAAAA…`); the plaintext never touches the column, a
  log line, or a response.
* **Retention-bounded** — `expires_at = now + MIGRATION_CLOUD_ARTIFACT_BLOB_RETENTION_DAYS`
  drives the daily purge, and a bundle's blobs are dropped the moment it reaches
  `RECONCILED`. **Artifact metadata is always retained** for the audit trail.
* **Size-bounded** — only artifacts ≤ `MIGRATION_CLOUD_ARTIFACT_BLOB_MAX_INLINE_BYTES`
  are stored inline; larger ones are skipped (logged, no PII) pending a file-backed
  Phase 2.
* **Tenant-isolated** — reachable only via `artifact → bundle → school`.

## Settings (all env / settings overridable)

| setting | default | meaning |
|---|---|---|
| `MIGRATION_CLOUD_ARTIFACT_BLOB_STORE_ENABLED` | `True` | master switch for NEW captures |
| `MIGRATION_CLOUD_ARTIFACT_BLOB_MAX_INLINE_BYTES` | `10 * 1024 * 1024` | inline size cap |
| `MIGRATION_CLOUD_ARTIFACT_BLOB_RETENTION_DAYS` | `7` | retention window |
| `MIGRATION_CLOUD_ARTIFACT_BLOB_DELETE_ON_RECONCILE` | `True` | drop source bytes on reconcile |

## Tests

`apps/migration_cloud/tests/test_artifact_blob_store.py` — 13 tests:
round-trip + **no plaintext at rest** + Fernet-token-present; archive member now
resolves via store / profiler / orchestrator; size-cap skip + at-cap allow;
retention sweep purges-expired-keeps-metadata; delete-on-reconcile + disabled-noop
+ end-to-end `reconcile_bundle`; flag-off no-op; sha256-mismatch ignored on read.
All pass; 19 existing intake/ingest/pull tests regression-clean;
`makemigrations --check` clean.

## Phase 2 (deferred)

File-backed store (object storage) for artifacts over the inline cap — the model
+ read path already tolerate a missing blob, so Phase 2 is additive.
