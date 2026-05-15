# Migration Cloud — Universal Intake (Phase U1)

This document explains the *source-agnostic intake layer* — the first phase of
the Universal Migration Cloud. The promise: a school can hand us anything
they have and the platform registers every artifact under one bundle without
the operator naming the source up front.

For the full 9-phase roadmap and architectural rationale see
`docs/MIGRATION_CLOUD_RUNBOOK.md` and the platform plan
`let-us-do-a-glistening-panda.md`.

## What "universal" means here

Five entry points, one pipeline:

```
   FILE_UPLOAD      ARCHIVE      URL / SFTP / S3      SQL_DUMP / DATABASE      OAUTH_FOLDER / EMAIL
        \             |                |                       |                          /
         \            |                |                       |                         /
          \           |                |                       |                        /
           \________________ universal pipeline ___________________________
                                       |
                               MigrationBundle
                                 + many MigrationArtifact
                                       |
                  → profiler (U2) → classifier (U3) → mapper (U4)
                  → orchestrator (U5) → wizard (U6) → reconciliation (U8)
```

Vendor accelerators (Phase U9) are a sixth entry point on the left side;
they short-circuit profile + classify + map by handing pre-classified
artifacts to the orchestrator. Importantly: **no accelerator gets its own
ingest path past the entry point**. If a vendor accelerator breaks, the
universal upload path is the safety net under it.

## Models (Phase U1)

| Model | Purpose |
|---|---|
| `MigrationBundle` | The whole data drop. Owns lifecycle (`PENDING → INGESTING → PROFILED → CLASSIFIED → MAPPED → READY → APPLYING → APPLIED → RECONCILED`). Has a stable `idempotency_key`; replays produce zero duplicates. |
| `MigrationArtifact` | One file/table/sheet within a bundle. Carries `sha256`, `mime_type`, `detected_format`, `byte_size`, optional `parent_archive` link so lineage is preserved when a zip is expanded. |

Bundles live in the **public schema** (django-tenants `SHARED_APPS`) so
platform operators can see every tenant's migration history from the
control plane. The `school` FK on the bundle is nullable so signup-time
bundles can be staged *before* the tenant schema exists; the orchestrator
binds the school at tenant provisioning time.

## Intake adapters

One adapter per source-shape, registered in
`apps/migration_cloud/intake/__init__.py`:

| Adapter | Method | Phase U1 status |
|---|---|---|
| `FileIntakeAdapter` | `FILE_UPLOAD` | Implemented |
| `ArchiveIntakeAdapter` | `ARCHIVE` (zip / tar / tar.gz / gz) | Implemented |
| `SqlDumpIntakeAdapter` | `SQL_DUMP` | Stub (Phase U7) |
| `DatabaseIntakeAdapter` | `DATABASE` | Stub (Phase U7) |
| `UrlIntakeAdapter` | `URL` / `SFTP` / `S3` | Stub |
| `OauthFolderIntakeAdapter` | `OAUTH_FOLDER` | Stub (Phase U7) |
| `EmailIntakeAdapter` | `EMAIL` | Stub (Phase U7) |

Stubs are deliberate: they keep the wizard's source-shape picker honest
(operators can list every shape with a "coming soon" affordance) without
breaking imports.

To add a new source-shape:

1. Create a new module under `apps/migration_cloud/intake/`.
2. Subclass `IntakeAdapter` and implement `iter_artifacts()`.
3. `register_adapter(IntakeMethod.X, MyAdapter())`.
4. Add the new `IntakeMethod` value in `apps/migration_cloud/models.py`.
5. Add the new method to the registry test in `tests/test_intake.py`.

## Orchestrator entry point

```python
from apps.migration_cloud.models import IntakeMethod
from apps.migration_cloud.services import BundleIngestionService, BundleSpec

result = BundleIngestionService().ingest(
    BundleSpec(
        intake_method=IntakeMethod.ARCHIVE,
        handle="/tmp/school_drop_2026_09.zip",
        school_id=42,
        schema_name="tenant_42",
        label="Sept 2026 cutover",
        idempotency_key="cutover-2026-09-school-42",
        triggered_by_id=operator.id,
    )
)
# result.bundle_id, result.artifacts_registered, result.artifacts_skipped_duplicate
```

The orchestrator handles tenant scoping, idempotency, deduplication, and
lifecycle state. Adapters never touch the DB directly — they yield
`ArtifactPayload` and the orchestrator persists. This keeps adapters
trivially unit-testable.

## Configurability (no hardcoding)

Every tunable value (MIME whitelist, extension allowlist, size caps, SLA
seconds, worker counts, confidence thresholds, retention window) is read
through `apps.migration_cloud.defaults.get(key)`. The cascade is:

```
env var (MIGRATION_CLOUD__*)  →  RuntimeDefaults.payload[key]  →  seeded fallback
```

The seeded fallback in `apps/migration_cloud/defaults.py::_SEED` is the
bottom of the 7-layer configurability contract — used only during bootstrap
before the `RuntimeDefaults` row materializes the value. To change a value
in production: edit `RuntimeDefaults.payload`; to hotfix without a deploy:
set the env-var override.

## Safety caps

Phase U1 enforces three caps to prevent runaway intake:

| Cap | Default | Override key |
|---|---|---|
| Max members per archive | 50,000 | `migration_cloud.intake.max_archive_members` |
| Max archive depth | 8 | `migration_cloud.intake.max_archive_depth` |
| Max bytes per artifact | 5 GiB | `migration_cloud.intake.max_artifact_bytes` |

Per-bundle byte caps differ by SLA tier (see the SLO table in the plan
file). Bundles that exceed their tier's cap should be upgraded to the next
tier rather than silently rejected.

## Lifecycle and where Phase U1 stops

Phase U1 only moves a bundle from `PENDING → INGESTING`. The bundle stays at
`INGESTING` until the Phase U2 profiler runs and moves it to `PROFILED`.
This makes the boundary between phases observable: every bundle stuck at
`INGESTING` is an unprofiled bundle, and the operator can re-trigger
profiling without re-running intake.

## Testing

`apps/migration_cloud/tests/test_intake.py` covers the smoke surface:

- FILE_UPLOAD with single path, list, mixed mime hints.
- ARCHIVE with zip + tar; member registration + parent-archive linkage.
- Idempotency: replay same key, same artifact → skip.
- Missing source → bundle marked FAILED, error captured.
- Every `IntakeMethod` resolves to an adapter (registry guard).
- Stub adapters raise `IntakeError` with a clear "Phase U7" message.

Run with: `python manage.py test apps.migration_cloud`.

## What lands next (Phase U2)

`apps/migration_cloud/profiler.py` reads each artifact's bytes once,
produces a deterministic `ArtifactProfile` (columns, inferred types,
sampled values, regex shape detection, PII flags, encoding, locale hints),
and transitions the bundle to `PROFILED`. Profiles are stored on
`MigrationArtifact.profile` and are byte-identical for identical input.
