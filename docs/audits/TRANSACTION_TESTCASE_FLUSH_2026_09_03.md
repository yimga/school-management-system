# TransactionTestCase flushes the whole database - audit 2026-09-03

**Status: OPEN. One instance fixed, the class is not closed.**

## What happens

Django's `TransactionTestCase` truncates **every table** at teardown (`_fixture_teardown`
calls `flush`) and does **not** roll it back. Against this repo's persisted keepdb SQLite
test database that damage is permanent: the migrations stay recorded as applied, so the
idempotent data-seed migrations never re-run, and every later test in that run *and every
later run reusing the file* sees an empty catalog.

`flush` re-emits `post_migrate`, which is why exactly one `AccessRole` survives -
`apps/accounts/superadmin_sync.on_post_migrate` recreates SUPERADMIN. Everything else
stays gone.

Granular RBAC resolves through `accounts_permission` / `accounts_accessrole`, so the
downstream symptom is unrelated suites returning **403** and looking like permission
regressions in code that is fine.

## Measured, not argued

A/B on `apps/apicenter/tests/test_api_center_open_and_usable.py`, same code, same
starting database, one arm each:

| table | `TestCase` | `TransactionTestCase` |
|---|---:|---:|
| `accounts_permission` | 46 | **0** |
| `accounts_accessrole` | 27 | **1** |
| `siteconfig_themepack` | 5 | **0** |

**Both arms reported `5 passed`.** The damage never appears in a test result. Do not look
for a red test - look at the row counts.

## Fixed

`ApiCenterOpenAndUsableTests` -> `TestCase` (commit `dedd0e6f7`). It needed no transaction
semantics; it arrived as a `TransactionTestCase` in the bulk "Ship v3.33 platform wave"
commit, so the choice was never reasoned.

## Still open: 28 files, 33 classes

Measured 2026-09-03 against `origin/main`. 40 files declare a `TransactionTestCase`; 11
are justified by real transaction semantics (threads, async/channels, `select_for_update`,
`on_commit`, explicit `atomic`, raw schema work, `IntegrityError`, `serialized_rollback`).
The rest carry **no such marker at all**:

- `apps/feedback/tests/base.py`
  - `FeedbackTestCase`
- `apps/migration_cloud/tests/test_bundle_84_repair_simulation_2026_08_21.py`
  - `Bundle84RepairSimulationTests`
- `apps/migration_cloud/tests/test_derived_report_skip_2026_08_13.py`
  - `ReportApplyLandsZeroTests`
- `apps/migration_cloud/tests/test_gap_fill_and_classroom_2026_08_13.py`
  - `GapFillAndClassroomEndToEndTests`
- `apps/migration_cloud/tests/test_gilead_ingest_ui_slice_2026_09_02.py`
  - `TelephoneDirectoryImportTests`
  - `MamaNoviSubjectsCategoryTests`
  - `MamaNoviFullBundleTests`
- `apps/migration_cloud/tests/test_guardian_hint_2026_08_13.py`
  - `GuardianHintIngestEndToEndTests`
- `apps/migration_cloud/tests/test_mama_novi_three_file_import_2026_08_21.py`
  - `MamaNoviThreeFileImportTests`
- `apps/migration_cloud/tests/test_report_card_readiness_2026_08_13.py`
  - `ReportCardScaffoldTests`
  - `ReportCardGeneratesAfterMigrationTests`
- `apps/migration_cloud/tests/test_rollback_completeness_2026_08_15.py`
  - `EnrollmentRollbackRestoresPriorValuesTests`
  - `FailedNonAtomicBundleRollsBackCommittedRowsTests`
- `apps/migration_cloud/tests/test_specialties_domain_and_lander_2026_08_13.py`
  - `SpecialtiesApplyTests`
- `apps/migration_cloud/tests/test_student_specialty_link_2026_08_13.py`
  - `StudentSpecialtyEndToEndTests`
- `apps/migration_cloud/tests/test_teacher_teaching_hints_2026_08_13.py`
  - `TeacherTeachingHintsEndToEndTests`
- `apps/migration_cloud/tests/test_trade_report_card_end_to_end_2026_08_13.py`
  - `TradeStudentReportCardEndToEndTests`
- `apps/people/tests/test_offline_credential_posture_2026_08_31.py`
  - `OperatorResetPasswordNotPersistedTests`
- `apps/schools/tests/test_founder_dashboard.py`
  - `FounderDashboardTests`
- `apps/schools/tests/test_marketing_validation.py`
  - `MarketingPublicRouteTransactionCase`
- `apps/schools/tests/test_operator_team_reset_password.py`
  - `OperatorTeamResetPasswordTests`
- `apps/schools/tests/test_super_dashboard_http.py`
  - `SuperDashboardHttpTests`
- `apps/schools/tests/test_super_offboarding_http.py`
  - `SuperOffboardingHttpTests`
- `apps/security/tests/test_absolute_security_enforcement.py`
  - `AbsoluteSecurityExportTests`
- `apps/security/tests/test_security_enforcement.py`
  - `ComplianceExportEnforcementTests`
  - `SecuritySurfaceDashboardTests`
- `apps/siteconfig/test_i18n.py`
  - `RegionalReportGeneratorTestCase`
- `apps/siteconfig/tests/test_operator_control_plane_shell.py`
  - `OperatorControlPlaneShellTests`
- `apps/siteconfig/tests/test_palette_generate_view.py`
  - `PaletteGenerateViewTests`
- `apps/siteconfig/tests/test_theme_builder.py`
  - `ThemeBuilderTests`
- `apps/siteconfig/tests/test_theme_experience_hub.py`
  - `ThemeExperienceHubTests`
- `apps/siteconfig/tests/test_theme_experience_plane_isolation.py`
  - `ThemeExperiencePlaneIsolationTests`
- `apps/studio_os/tests/test_studio_os_world_class_experience.py`
  - `StudioOsWorldClassExperienceTests`

Excluded as deliberate: `apps/test_utils/tenant_hosts.py::TenantHostTransactionTestCase`
is a named base class, intentionally a `TransactionTestCase`.

**The absence of a marker is a signal to review, not proof it is safe to convert.** Some
of these may have been made `TransactionTestCase` because they failed under `TestCase`
for reasons this heuristic cannot see. Each needs its own A/B.

## The systemic fix, and why it was NOT applied

`flush` re-emits `post_migrate`, and this repo already exploits that for exactly one row.
Moving the rest of the catalog seeding into an idempotent `post_migrate` receiver would
make every flush self-heal and close all 33 at once, without touching a single test.

It is deliberately not attempted here. Re-seeding this catalog mid-investigation
previously turned 0 failures into **2** in the grade-approval cluster, because some tests
were passing only because permission was denied early - granting it changed their path.
The change also runs on every production `migrate`. That blast radius is an owner's
decision, not a drive-by fix.

## Reproducing the measurement

1. Build a test DB, then record `SELECT COUNT(*)` for `accounts_permission`,
   `accounts_accessrole`, `siteconfig_themepack`.
2. Copy the sqlite file aside - the run is destructive.
3. Run any module containing one of the classes above with `PYTEST_KEEPDB=1`.
4. Re-read the counts. Restore the copy.

Until this is closed, order any `TransactionTestCase` module **last** on the pytest
command line so everything before it runs against seeded data.
