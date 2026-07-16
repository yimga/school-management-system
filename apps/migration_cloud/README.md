# apps/migration_cloud

> Take a school's entire legacy data drop — any shape, any vendor — profile it,
> classify it, map it to the canonical ontology, and land it in the tenant
> schema with a financial guardrail and a reconciliation report.

**Tenancy:** SHARED (bundle + artifact + audit metadata live in the public schema; the apply step writes into the tenant schema via an explicit `schema_context`)
**Scale:** 19 models · 39 migrations · 97 test modules · ~81k LOC

## What this app owns

Migration Cloud is how a school leaves its old SIS. It owns the whole path from
"here is a zip of whatever we had" to "the rows are in your tenant and here is
proof they are faithful". A `MigrationBundle` is the whole school's data drop
regardless of shape; a `MigrationArtifact` is one file/table/sheet inside it,
including members unpacked from a parent archive or exploded out of a multi-sheet
workbook.

The architecture is a strict phase pipeline, each phase a separate module with a
single entry point, and the bundle's status is the state:

```
PENDING -> INGESTING -> PROFILED -> CLASSIFIED -> MAPPED -> READY
        -> APPLYING -> APPLIED -> RECONCILED
                    \-> FAILED / ABORTED
```

`services.BundleIngestionService.ingest` brings bytes in and deliberately stops
at INGESTING. `pipeline.advance_bundle` is the single entry point for the
AI-assisted phases (profile → classify → map) and is idempotent — an already-MAPPED
bundle is a no-op, a partially advanced one picks up at the next step.
`orchestrator.apply_bundle` lands rows. `reconciliation.reconcile_bundle` produces
the trust artifact.

Two decisions define the app. First, **determinism is pushed as early as
possible and AI as late as possible**: the profiler must produce the same dict
byte-for-byte for the same bytes (deterministic sampling, no randomness), the
mapper runs a cheapest-first layer stack (exact alias → token similarity →
value-shape check) and only calls the LLM as a tiebreaker when those miss the
confidence threshold — and the apply step calls the AI gateway *never*. Second,
**no data loss anywhere**: a column with no candidate over threshold becomes
`custom_fields.<normalized>` and lands in the tenant's DynamicField storage; a
row that fails transformation or upsert lands in
`apps.automation.MigrationQuarantineRecord` with the source row and error
attached, visible in the wizard.

## Key models

All 19 models the app declares, grouped by the layer they serve.

| Model | Table | Purpose |
| --- | --- | --- |
| `MigrationBundle` | `migration_cloud_migrationbundle` | The whole school's data drop. Owns the lifecycle, `expected_totals` (the operator's control totals), and `reconciliation_summary`. |
| `MigrationArtifact` | `migration_cloud_migrationartifact` | One file/table/sheet within a bundle; deduped on `sha256 + path_within_bundle`. |
| `MigrationArtifactBlob` | `migration_cloud_migrationartifactblob` | Fernet-encrypted-at-rest copy of one artifact's source bytes (the Phase U5 content store). |
| `MigrationAsset` | `migration_cloud_migrationasset` | One binary asset — student photo, immunization scan, report-card PDF. |
| `MigrationIdMapping` | `migration_cloud_migrationidmapping` | Audit table mapping legacy source IDs to the canonical tenant rows they became. |
| `MigrationConflict` | `migration_cloud_migrationconflict` | An upsert conflict surfaced during apply — the operator review surface. |
| `MigrationProgressEvent` | `migration_cloud_migrationprogressevent` | Append-only timeline behind the DAG view and the SSE progress stream. |
| `MigrationIntakeRequest` | `migration_cloud_migrationintakerequest` | A school-side request to migrate from a named SIS vendor. |
| `MigrationCloudAuditEvent` | `migration_cloud_migrationcloudauditevent` | Tamper-evident, append-only forensic trail with a per-tenant SHA-256 hash chain. |
| `MigrationAuthorizationAgreement` | `migration_cloud_migrationauthorizationagreement` | The operator's signed authorization that they have the legal right to migrate this data. Stores the verbatim signature text (and its SHA-256) as of signing. |
| `MAAActiveVersionState` | `migration_cloud_maaactiveversionstate` | Singleton tracking which MAA version is currently active. |
| `MigrationCloudCounselAttestation` | `migration_cloud_migrationcloudcounselattestation` | Append-only record of counsel attestations gating an MAA promotion. |
| `MigrationCloudMAACampaignNotification` | `migration_cloud_migrationcloudmaacampaignnotification` | Idempotency record for MAA v2.0 re-sign campaign email. |
| `MigrationCloudCompanionKeypair` | `migration_cloud_migrationcloudcompanionkeypair` | Per-tenant server-side X25519 keypair used to seal/open Companion bundles; private half encrypted at rest, one active row per tenant. |
| `CompanionUploadReceipt` | `migration_cloud_companionuploadreceipt` | Append-only record of every accepted Companion upload; unique on `client_idempotency_key`. |
| `CompanionCiphertextBlob` | `migration_cloud_companionciphertextblob` | The encrypted bundle bytes received from a Companion upload. |
| `MigrationCloudAPIToken` | `migration_cloud_migrationcloudapitoken` | Opaque scoped token for the Migration Cloud REST API; only its SHA-256 is persisted. |
| `MigrationCloudWebhookSubscription` | `migration_cloud_migrationcloudwebhooksubscription` | Partner-registered outbound webhook endpoint; secret stored as ciphertext. |
| `MigrationCloudWebhookDelivery` | `migration_cloud_migrationcloudwebhookdelivery` | One delivery attempt with retry/backoff FSM and replay lineage. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `services` | `BundleIngestionService.ingest` — the ONE entry for bringing bytes in. Stops at INGESTING by design. |
| Module | `pipeline` | `advance_bundle(bundle_id, use_accelerator=)` — the ONE entry for profile → classify → map. Idempotent. |
| Module | `profiler` | Phase U2. Deterministic `ArtifactProfile` (format, encoding, per-column type inference, PII flags, locale hints). |
| Module | `mapper` | Phase U4. Cheapest-first mapping layers; AI tiebreaker last; unmapped columns become `custom_fields.*`. |
| Module | `orchestrator` | Phase U5. `apply_bundle(bundle_id, dry_run=, workers=)` — deterministic, tenant-scoped, records one `MigrationRun` per (domain, artifact). |
| Module | `guardrails` | `enforce_financial_guardrail` — control totals must match before APPLIED; raises `FinancialMismatchError`. |
| Module | `reconciliation` | Phase U8. Per-domain parity, fill-rate scorecards, stratified sample rows, idempotency check. |
| Module | `repair` | Conservative, idempotent re-apply of a stalled/failed bundle; `repair_readiness` refuses the unsafe cases. |
| Module | `artifact_blob_store` | The one place that captures / reads / purges the encrypted source-byte copies. |
| Module | `companion_receiver` | MAA text + sign, sealed-box upload, staff-only in-memory decrypt hook. |
| Module | `models_audit` | The append-only hash-chained audit event + its `_sanitize_payload` write-time rejection list. |
| Module | `xlsx_explode`, `pdf_extract` | Multi-sheet workbook explosion and PDF table extraction at intake. |
| Celery task | `advance_bundle_task`, `apply_bundle_task` | Async pipeline + apply. |
| Celery task | `fetch_assets_task` | Pulls binary assets referenced by a bundle. |
| Celery task | `deliver_due_task` | Webhook delivery drain. |
| Celery task | `purge_completed_migration_bundles_audit_task` | Retention purge of completed bundles. |
| Celery task | `run_smoke_on_demand` + the smoke/archival/token-rotation/audit-chain watchdogs | Operational assurance. |
| Command | `verify_audit_chain` | Walks the per-tenant hash chain. Exit 0 clean / 1 broken / 2 signature mismatch (backup-restore tamper signal). |
| Command | `purge_audit_events_pre_approved` | Refuses to run without the counsel approval token; dry-run by default. |
| Command | `promote_maa_v2`, `maa_v2_resign_campaign` | MAA promotion plumbing. |
| Command | `migration_cloud_smoke`, `migration_cloud_smoke_multi`, `migration_cloud_rotation_drill` | Smoke + key-rotation drills. |
| Command | `promote_dyna_assignments`, `replay_dfv_assignments` | Dynamic-field → first-class assignment promotion. |
| Command | `seed_migration_connector_profiles`, `cleanup_intake_uploads`, `dsar_runbook_record` | Connector seed, intake hygiene, DSAR records. |
| URL | `bundle_new` / `bundle_detail` / `bundle_preflight` / `bundle_apply` / `bundle_progress[_stream]` / `bundle_conflicts` / `bundle_repair` / `audit_dashboard` / `audit_export` | Wizard, operator, and tenant-upload surfaces, mounted across the tenant and manager hosts. |

## Before you change this

- **This app is SHARED but writes into TENANT schemas.** Bundle, artifact, and
  audit metadata live in the public schema; `orchestrator.apply_bundle` wraps all
  persistence in `django_tenants.utils.schema_context(bundle.schema_name)`. If you
  add a write path, decide explicitly which side of that boundary it belongs on —
  getting it wrong silently lands student rows in the wrong schema.
- **Never suppress `FinancialMismatchError`.** The financial guardrail is the
  app's strongest trust signal: the operator's control totals must match the
  post-apply observed totals (default tolerance 0.01 absolute / 0.001 relative,
  for rounding drift) or the apply aborts rather than leave a half-applied ledger.
  `repair.repair_readiness` refuses a guardrail failure outright, and refuses
  finance artifacts unless the apply is `apply_atomic` — a partial finance
  re-apply could double-count or leave money half-written.
- **`repair_bundle` is deliberately conservative, and the refusals are the
  feature.** It will not touch a `RECONCILED` bundle (source blobs are already
  purged and it is confirmed good), an `APPLYING` one, an `ABORTED` one, or a
  pre-`MAPPED` one. It is one explicit operator click, never a silent background
  retry, because a live re-import writes to the tenant DB.
- **The profiler must stay deterministic.** Re-profiling the same bytes must
  produce the same dict byte-for-byte — the classifier, mapper, and transformers
  all read it. Sampling is first-N plus a stratified middle sample, with no
  randomness. It also degrades gracefully rather than blocking: a bad artifact is
  profiled with what it has, and the classifier sees the partial profile.
- **The apply step must never call the AI gateway.** All AI happens earlier (in
  the mapper and classifiers). Apply is deterministic — that is what makes a
  re-apply safe and a rollback meaningful. (App code that does need AI routes
  through `ai_bridge`, which is one of the few allowlisted `services.ai_gateway`
  importers.)
- **Lander kwargs must be real model fields.** `scan_lander_phantom_fields.py` is
  a zero-tolerance gate born from real silent-data-loss bugs: a lander passing a
  non-field kwarg to `.create` / `.get_or_create` raises `TypeError`/`FieldError`,
  a broad `except` swallows it, and the row vanishes. Route non-fields through
  `filter_to_model_fields` or the DynamicFieldValue engine.
- **The audit log is append-only and hash-chained, and both halves are enforced
  in code.** `save()` on an existing `MigrationCloudAuditEvent` raises; `delete()`
  always raises; each event's `integrity_hash` covers a canonical JSON pre-image
  that includes the previous event's hash for the same tenant (first event uses
  the `"genesis"` sentinel). `_sanitize_payload` REJECTS sensitive keys at write
  time, so payload summaries never carry PII or secret material — tenant slug,
  user email, and subject UUID are stored only as SHA-256-derived hex prefixes.
- **Never log bytes.** The Companion receiver, the blob store, and the key
  services all emit IDs and lengths only — never ciphertext, plaintext, keys, or
  MAA `signature_text`. `scan_pii_logging_smell.py` enforces this, and existing
  tests use `assertLogs` to prove it.
- **MAA draft versions can never be signed.** Three independent gates guarantee a
  draft body is never captured as a signature; the v2.0 body ships as a DRAFT
  pending counsel signoff and the default stays v1.0. Promotion is a documented
  config flip (`docs/MAA_V2_PROMOTION_CHECKLIST.md`), not a code edit, and historic
  signature rows are never deleted on rollback.
- **Vendor data extraction does not live here, and that boundary is legal, not
  technical.** Extraction from PowerSchool / Blackbaud / Veracross / Alma /
  FACTS / Skyward happens in the operator's own authenticated browser tab
  (`companion-extension/`); the Tauri and Docker siblings only do the RunMyCampus
  handshake and canonical-CSV ingest. FACTS and Skyward *write* paths remain
  honest stubs pending the counsel docket
  (`docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`) — a default-off feature flag
  is explicitly not an acceptable workaround.
- **Source bytes are student PII on a retention clock.** `MigrationArtifactBlob`
  is Fernet-encrypted at rest, size-bounded by an inline cap, expires on a
  retention window, is dropped when the bundle reaches RECONCILED, and is
  reachable only via `artifact → bundle → school`. Do not add a code path that
  keeps them longer or reads them outside `artifact_blob_store`.
