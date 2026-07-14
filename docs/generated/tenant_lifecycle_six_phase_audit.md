# Tenant Lifecycle Six-Phase Audit

Overall status: `PASS_WITH_WORKTREE_WARNINGS`

## Phase Summary

| Phase | Status | Passing | Failed checks |
| --- | --- | ---: | --- |
| Discovery, evaluation, signup, provisioning, isolation | `PASS` | 10 / 10 | None |
| Configuration, branding, localization, rules, integrations | `PASS` | 8 / 8 | None |
| Data migration and ingestion | `PASS` | 8 / 8 | None |
| Steady-state school operations | `PASS` | 9 / 9 | None |
| Maintenance, scaling, tenant audit, support | `PASS` | 7 / 7 | None |
| Offboarding, export, suspension, purge | `PASS` | 8 / 8 | None |
| Tenant/operator separation | `PASS` | 6 / 6 | None |
| Truth ledger and redundancy control | `PASS` | 3 / 3 | None |

## Tenant Routes

| Check | Status | URL | Failure |
| --- | --- | --- | --- |
| `public_signup` | `PASS` | `/signup/` |  |
| `public_verify_signup` | `PASS` | `/verify-signup/` |  |
| `tenant_provisioning_status` | `PASS` | `/school/studio/provisioning/` |  |
| `tenant_configuration` | `PASS` | `/school/configuration/` |  |
| `tenant_blueprints` | `PASS` | `/school/setup/blueprints/` |  |
| `tenant_packs` | `PASS` | `/school/setup/packs/` |  |
| `tenant_imports` | `PASS` | `/school/setup/imports/` |  |
| `tenant_migration_cloud` | `PASS` | `/school/setup/migration-cloud/` |  |
| `tenant_migration_upload` | `PASS` | `/school/setup/migration-cloud/upload/` |  |
| `tenant_app_catalog` | `PASS` | `/settings/app-catalog/` |  |
| `tenant_offboarding` | `PASS` | `/school/studio/offboarding/` |  |

## Gates

| Script | Status |
| --- | --- |
| `scripts/audit_tenant_lifecycle_aggressive.py` | `PASS` |
| `scripts/verify_tenant_lifecycle_unified.py` | `PASS` |
| `scripts/verify_migration_cloud_intake_experience.py` | `PASS` |
| `scripts/audit_blueprint_local_first_offline.py` | `PASS` |

## Worktree Warnings

- active render-audit worktree and canonical school-management-system worktree are on different commits
- canonical local school-management-system worktree is behind origin/main
- canonical local school-management-system worktree has uncommitted changes

## Failed Probe Details

None

## Interpretation

- PASS means repo-side lifecycle wiring is present and focused gates pass.
- PASS_WITH_WORKTREE_WARNINGS means repo-side wiring passes, but local worktree drift can explain deployment confusion.
- This audit does not claim external vendor readiness, production PostgreSQL/RLS proof, or real DNS/email/PSP completion unless separate environment evidence exists.
