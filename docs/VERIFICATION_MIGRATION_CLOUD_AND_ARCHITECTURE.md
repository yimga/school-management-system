# Verification: Migration Cloud and Platform Architecture

This document lists how to verify that the Migration Cloud blueprint implementation and related features are complete and working.

## 1. Migrations and seed

```bash
python manage.py migrate automation
python manage.py seed_migration_profiles
```

- **Check:** No migration errors. After seed, `MigrationProfile` has FACTS, Skyward, Alma, and `phased_migration`; `profile_category` is set on vendor profiles.
- **Check:** `MigrationPlaybook` and `MigrationQuarantineRecord` tables exist.

## 2. Schema fingerprinting

- **Module:** `apps.automation.schema_fingerprint`
- **Function:** `suggest_profiles_from_headers(headers, domain=None, min_confidence=0.0)` returns list of `(profile, confidence)` sorted by confidence.
- **Check (in shell):** After seed, call `suggest_profiles_from_headers(["student_number", "first_name", "last_name", "grade_level"])` and confirm at least one profile (e.g. students_from_powerschool) is returned with confidence > 0.

## 3. Repair and quarantine

- **Models:** `MigrationQuarantineRecord` (school, migration_run, domain, row_index, payload, issue_class, status, resolution_payload).
- **Module:** `apps.automation.quarantine_services`: `add_to_quarantine`, `mark_repaired`, `get_repaired_rows`.
- **Check (in shell):** Create a quarantine record with `add_to_quarantine`, call `mark_repaired` with a resolution payload, then `get_repaired_rows(domain="students")` returns one row.

## 4. Migration Playbook and executor

- **Model:** `MigrationPlaybook` with `profile_slugs` and `get_profiles()`.
- **Module:** `apps.automation.playbook_executor`: `execute_playbook(playbook, school, user, dry_run, steps_payload)`.
- **Check (in shell):** Create a playbook with two profile slugs, call `execute_playbook(playbook, school=None, user=None, dry_run=True, steps_payload=None)` and confirm result has `runs` of length 2 and `status == "SUCCESS"`.

## 5. Super UI: Migration Profile Registry

- **URL:** `/super/migration/registry/` (with super access).
- **Check:** Page loads and shows profiles grouped by source_system and profile_category. Link from Migration Cloud page to Registry works.

## 6. Blueprint docs

- **Check:** These files exist and state that every requirement is non-negotiable:
  - `docs/RunMyCampus_Migration_Cloud_Complete_System_Blueprint.md`
  - `docs/RunMyCampus_AI_Architecture_and_Model_Improvement.md`
  - `docs/RunMyCampus_Complete_Platform_Architecture_Diagram.md`

## 7. Automated tests

```bash
python manage.py test apps.automation.tests.test_migration_cloud_phase_a -v 2
```

**Test classes:**

- `MigrationProfileSourceSystemTests` — SourceSystem choices (including FACTS, Skyward, Alma), profile_category, seed profiles.
- `SchemaInferenceTests` — infer_schema_mapping (existing).
- `PreMigrationValidationTests` — run_pre_migration_validation (existing).
- `MigrationPlaybookTests` — get_profiles ordered, empty when no slugs.
- `SchemaFingerprintTests` — suggest_profiles_from_headers (PowerSchool-like headers, empty headers).
- `QuarantineTests` — add_to_quarantine, mark_repaired, get_repaired_rows.
- `PlaybookExecutorTests` — execute_playbook dry_run with empty payload creates two runs.

**Note:** The first run can take several minutes due to applying all migrations. Use `--keepdb` on subsequent runs to reuse the test database.

## 8. Admin

- **Check:** In platform admin, Migration Profile list shows `profile_category`; Migration Playbook and Migration Quarantine Record are registered and list/detail work.
