# RunMyCampus Migration Cloud — Complete System Blueprint

**Every requirement in this document is non-negotiable.** This is the single source of truth for the Migration Cloud. No item is optional or deferred.

## Purpose and strategic thesis

Migration is the platform moat. The north star is "easy to switch to RunMyCampus." Schools must be able to move from any major SIS (PowerSchool, Blackbaud, Veracross, Infinite Campus, FACTS, Skyward, Alma, generic CSV/API/SQL) with minimal friction: upload or connect, map, validate, repair if needed, dry-run in a sandbox, then cut over with verification and rollback safety.

## Core engines (with touchpoints in repo)

### Source connector engine

- **Vendors:** PowerSchool, Blackbaud, Veracross, Infinite Campus, FACTS, Skyward, Alma, generic CSV SIS, generic API SIS, SQL export.
- **Methods:** API, file upload, DB, SFTP, cloud.
- **Ref:** `MigrationProfile.format`, `source_system`, wizard upload (`accounts.migration_wizard`).

### Schema fingerprint / profile detection engine

- **Required:** Implement schema inference (table/column names, types, relationship patterns; confidence scores and auto-load profile). Wizard mapping is the current baseline.
- **Implemented:** `apps.automation.schema_fingerprint.suggest_profiles_from_headers(headers, domain=None, min_confidence=0.0)` scores active MigrationProfiles with schema_hints against column headers and returns (profile, confidence) list for auto-load or suggestion.
- **Touchpoint:** Migration wizard (`accounts.views_migration`) calls `suggest_profiles_from_headers` when CSV headers exist and shows ranked profile suggestions in the mapping step. **Execution checklist and Ollama/gateway role:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §0.1.2 (implementation audit & action queue)—do not duplicate that content here.

### Canonical education translation layer

- **Entities:** Person, Student, Guardian, Staff, Enrollment, Course/Section, Assessment/Grade, Attendance, Invoice/Payment, Document, Communication, Custom fields.
- **Ref:** [MIGRATION_CANONICAL_FIELDS.md](MIGRATION_CANONICAL_FIELDS.md), [CANONICAL_OBJECTS_MAPPING.md](CANONICAL_OBJECTS_MAPPING.md).

### Mapping engine

- Profiles, AI inference, manual overrides, playbooks; auto-map, confidence, bulk remap, preview.
- **Ref:** `accounts.migration_wizard`, session mapping, `MigrationProfile.config`.

### Validation engine

- Schema, field, relationship, policy, operational readiness.
- **Ref:** Dry-run in `migration_services`, evals `dry_run_grade_import`.

### Repair and quarantine engine

- **Required:** Quarantine bad records; merge duplicates, placeholders, remap, normalize; replay repaired subset.
- **Implemented:** `MigrationQuarantineRecord` model (school, migration_run, domain, row_index, payload, issue_class, status, resolution_payload). Service: `apps.automation.quarantine_services.add_to_quarantine`, `mark_repaired`, `get_repaired_rows` for guided repair and replay.

### Dry-run / sandbox engine

- **Required:** Full temporary tenant sandbox for preview and reset. Dry-run flag on MigrationRun is current baseline; full sandbox tenant is required.

### Execution and delta sync engine

- Dependency order, parallel pipelines, incremental/phased, current-year-first, delta sync.
- **Ref:** MigrationRun, execution order in services.

### Verification and rollback engine

- Scorecard, count comparison, sample parity, launch checklist, rollback checkpoints.
- **Ref:** `MigrationRun`, `compute_parity`, rollback handlers in automation.

## Full migration profile library

- **Vendor:** PowerSchool, Blackbaud, Veracross, Infinite Campus, FACTS, Skyward, Alma, generic CSV SIS, generic API SIS, SQL export.
- **Institution-type:** private school, public school, district, school network, TVET, tertiary/university, international/IB, faith-based, multilingual.
- **Geography/policy:** US district K–12, UK GCSE/A-Level, Francophone/Anglophone Africa, UAE/Gulf, IB international, bilingual.
- **Data-condition:** clean, fragmented, legacy-archive, minimal current-year, duplicate-heavy, admissions-heavy, finance-heavy.
- **Strategy:** fast launch, phased, zero-downtime, sandbox-first, district rollout, campus-by-campus.
- **Composite profile chaining:** Required. Combine e.g. PowerSchool + district K–12 + fragmented + phased via MigrationPlaybook or composite config; configures mappings, validation, repair, cutover, verification.

## Migration playbooks

- Reusable playbooks (e.g. single-campus private, district K–12, TVET): pre-select profiles, validation rules, import order, dry-run sequence, go-live checklist. Link to blueprint packs and marketplace. Required.

## Marketplace and migration

- Migration packs as marketplace assets; partner-published profiles; migration marketplace.
- **Ref:** [phase8_migration_cloud_and_marketplaces.md](architecture/phase8_migration_cloud_and_marketplaces.md).

## Seeding strategy

- First-party migration profiles seeded via `seed_migration_profiles`; extend seed list to match the profile library above. Required.

## Overlooked areas (all non-negotiable)

- Permissions migration
- Document migration
- Communications migration
- Custom fields migration
- Report/template parity
- Support handoff

## Additional Migration Cloud improvements (all non-negotiable)

- Object-by-object readiness scoring per domain
- Dependency-aware import ordering
- Record quarantine (no full-stop failure) with guided repair by issue class
- AI-assisted repair proposals with human approval
- Full dry-run tenant sandbox
- Verification packs (count reconciliation, sample checks, exception list)
- Side-by-side source vs target compare
- Incremental/phased modes and delta sync before cutover
- Post-migration launch checklist
- Minimal-clicks UX
- URL/domain transition support

## Non-negotiable next actions

- Rollback UI, legacy cleaner, read-only legacy view
- Schema fingerprinting, repair/quarantine, sandbox tenant, delta sync
- Profile registry and playbooks (MigrationPlaybook + multi-step executor)

## References

- [phase5_migration_cloud.md](architecture/phase5_migration_cloud.md)
- [phase8_migration_cloud_and_marketplaces.md](architecture/phase8_migration_cloud_and_marketplaces.md)
- [MIGRATION_CANONICAL_FIELDS.md](MIGRATION_CANONICAL_FIELDS.md)
- MIGRATION_CLOUD_RUNBOOK (when created)
