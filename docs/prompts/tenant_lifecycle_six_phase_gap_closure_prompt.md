# Tenant Lifecycle Six-Phase Gap Closure Prompt

Use this prompt when RunMyCampus needs a full tenant-lifecycle audit and gap-closure pass. Do not assume coverage from old generated docs.

## Objective

Audit, fix, test, validate, and re-audit the tenant lifecycle from discovery through offboarding so the platform can honestly operate like a world-class local-first, offline-first school operating system.

The platform must never fake readiness. External DNS, email, payment, legal, production PostgreSQL/RLS, and vendor integrations remain `EXTERNAL_BLOCKED` until real environment evidence exists.

## Required Audit First

Run:

```powershell
$env:SECRET_KEY='dev-secret-key-for-audit'
python scripts\audit_tenant_lifecycle_six_phase.py
python scripts\audit_tenant_lifecycle_full.py
python scripts\verify_tenant_lifecycle_unified.py
python scripts\verify_migration_cloud_intake_experience.py
python scripts\audit_blueprint_local_first_offline.py
```

Read and reconcile:

- `docs/generated/tenant_lifecycle_six_phase_audit.md`
- `docs/generated/tenant_lifecycle_six_phase_audit.json`
- `docs/generated/tenant_lifecycle_forensic_gap_audit.md`
- `docs/generated/blueprint_local_first_offline_audit.md`
- `docs/generated/migration_cloud_connector_discovery.md`

## Six Phases To Prove

1. **Discovery, evaluation, signup, provisioning, isolation**
   - Public signup, plan selection, migration intent, verification email, tenant workspace provisioning, data residency, tenant admin route, and isolated tenant runtime.
   - Tenant backend admin must be tenant-owned and cannot route to the operator admin.

2. **Configuration, branding, localization, rules, integrations**
   - Tenant configuration center, onboarding checklist, Theme & Experience preview, country/localization packs, academic year setup, grading, attendance, terms, integrations, and custom domain posture.

3. **Data migration and ingestion**
   - Migration Cloud tenant route, upload, review, live progress, repair, control totals, post-apply verification, CSV import, baseline proof, and migration audit chain.
   - Migration success must mean rows landed and are visible to the tenant, not just that a file uploaded.

4. **Steady-state operations**
   - Tenant dashboard, users/RBAC, attendance, gradebook, reports, finance, communications, workflows, app catalog, offline storage, offline replay handlers, and tenant-only daily operations.

5. **Maintenance, evolution, scaling**
   - Subscription/package lifecycle, payment readiness, tenant audit logs, support portal, app installs, configuration change requests, health signals, and non-disruptive update posture.

6. **Offboarding and deprovisioning**
   - Tenant self-service closure, export/download, wind-down/read-only mode, commerce/enrollment write guards, inventory, purge operations, operator approval, backup purge honesty, and cancellation window.

## Tenant/Operator Boundary Rules

- No tenant URL may redirect to `/super/` or operator `/admin/` unless it is an explicit operator-only action.
- Tenant pages must only show tenant-safe blueprints, tenant-safe apps, tenant-scoped audit logs, and tenant-scoped configuration.
- Operator-only blueprint/app controls must stay hidden on tenant hosts.
- Cross-tenant access must return 404 or deny without leaking whether the other tenant exists.

## Migration Cloud Rules

- Tenant Migration Cloud must support file-first local/offline realities: CSV, XLSX, PDF, ZIP, canonical export, and vendor handoff.
- Every tenant import path must show one primary next action, clear blockers, live progress, row/domain detection, repair path, and post-apply verification.
- Control totals and baseline reconciliation must cover students, guardians, staff, enrollments, grades, attendance, timetable, fees, and balances where applicable.

## Blueprint And App Catalog Rules

- Tenant-safe blueprints must support base + regional + offline + specialty overlay composition.
- Support schools that run multiple tracks at once, such as general plus technical/vocational education.
- Blueprint preview must show local-first/offline impact, compatible blueprints, country/region constraints, app recommendations, and approval requirements.
- App catalog installs must be tenant-scoped, reversible where possible, permission-aware, and honest about external blockers.

## Redundancy And Truth Rules

- Reconcile stale generated docs instead of adding another conflicting proof file.
- If multiple lifecycle state machines exist, identify the canonical operational state machine and document read-only helper layers.
- If local worktrees differ from `origin/main`, report it as a deployment-risk warning. Do not silently patch the wrong worktree.

## Fix Loop

For every failing audit item:

1. Identify the exact file, route, template, service, or test gap.
2. Patch the smallest owner-boundary-respecting fix.
3. Add or update focused tests or audit probes.
4. Re-run the six-phase audit and affected focused tests.
5. Repeat until the audit is `PASS` or `PASS_WITH_WORKTREE_WARNINGS` only.

## Validation Floor

Run:

```powershell
$env:SECRET_KEY='dev-secret-key-for-audit'
python manage.py check
python manage.py makemigrations --check --dry-run
python -m compileall -q apps config scripts
python scripts\audit_tenant_lifecycle_six_phase.py
python scripts\audit_tenant_lifecycle_full.py
python scripts\audit_approved_html_implementation.py
python scripts\audit_django_surface_platformwide_contract.py
```

If a Django test suite is blocked by local SQLite schema drift or stale test DB prompts, document the exact blocker and still run static/import/direct smoke validations.
