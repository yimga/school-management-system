# Baseline report (Wave 0)

**Purpose:** Snapshot at start of Three Plans execution. Use this as the reference baseline; quality gates must pass on main before marking Wave 0 done.

## Baseline scope

- **Checklist:** [THREE_PLANS_MERGED_CHECKLIST.md](THREE_PLANS_MERGED_CHECKLIST.md)
- **Execution guide:** [THREE_PLANS_EXECUTION_GUIDE.md](THREE_PLANS_EXECUTION_GUIDE.md)
- **Parts:** A (Branded Login) → B (Wave 0) → C (Wave 1) → D–G

## Quality gates (Wave 0)

| Gate | How to run | Pass criteria |
|------|------------|----------------|
| Migrations check | `python manage.py makemigrations --check --dry-run` | No unapplied model changes |
| Django check | `python manage.py check` | No system errors |
| Tenant model audit | `python manage.py audit_tenant_models --strict` | Strict tenant audit passes |
| Smoke URLs | `python manage.py test apps.accounts.tests.test_smoke_urls` | Critical URLs resolve |
| Phase / RBAC | `python manage.py test apps.siteconfig.tests.test_admin_ui_smoke apps.api.tests.test_dashboard_api_rbac` | Targeted tests pass |
| Multi-tenant / provisioning | `python manage.py test apps.schools.tests.test_tenant_isolation_and_provisioning` | Isolation and provisioning tests pass |

**CI:** `.github/workflows/smoke.yml` runs `scripts/pre_deploy_gate.sh` on push/PR to main. Optional: add a docs lint step (e.g. markdownlint for `docs/`) to the workflow if desired.

## Verification (Done when)

| Criterion | Status | Where |
|-----------|--------|--------|
| Baseline report exists | Done | This file (`docs/baseline_report.md`) |
| All gates defined and runnable | Done | Table above; `scripts/pre_deploy_gate.sh` (Django check, no hardcoding, lint_tenant_settings, makemigrations --check, audit_tenant_models, smoke URLs, theme matrix, phase checks, core workflows, multi-tenant tests, render startup refs) |
| CI runs gates on main | Done | `.github/workflows/smoke.yml` runs `bash scripts/pre_deploy_gate.sh` on push/PR to main |
| Release checklist skeleton | Done | [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) (pre-release, build, deploy, post-release) |

To confirm "all gates green on main": run `bash scripts/pre_deploy_gate.sh` locally or open the latest run of the Smoke test workflow on the main branch and ensure it passed.

## Wave deliverables (reference)

| Wave | Theme | Key deliverable |
|------|--------|------------------|
| W1 | Deployment speed & trial | Minimal create, trial API, contact_email required, seed classrooms, first-login checklist |
| W2 | Onboarding & ease of use | Empty states, help links, breadcrumbs, error messages |
| W3 | Flexibility engine | Tenant enums, validation rules, feature gates, theme pack |
| W4–W17 | Per execution guide | See [THREE_PLANS_EXECUTION_GUIDE.md](THREE_PLANS_EXECUTION_GUIDE.md) Part F |

**Done when:** Baseline report exists (this file), all gates green on main, release checklist skeleton in place. All three are in place: see Verification table above; gates are run by CI on every push/PR to main.
