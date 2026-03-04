# Master Table List (tenant schema)

Part 0. Canonical list of tables created in **every new tenant schema**. Onboarding runs `migrate` (via `_run_tenant_migrations`) which applies all TENANT_APPS migrations; the result is one set of tables per schema.

## Tenant apps (config/settings.py TENANT_APPS)

| App | Tables (prefix) | Purpose |
|-----|----------------|---------|
| apps.academics | academics_* | AcademicYear, Term, Classroom, Subject, Specialty, Department, etc. |
| apps.people | people_* | StudentProfile, TeacherProfile, Guardian, InformationTag, TenantAuditLog (audit_log), etc. |
| apps.finance | finance_* | Invoice, Payment, LedgerAccount, FeePlan, etc. |
| apps.evals | evals_* | Evaluation, Grade, Assignment, etc. |
| apps.reports | reports_* | ReportCard, ReportRequest, etc. |
| apps.communication | communication_* | Announcement, NarrativeFeedback, etc. |
| apps.analytics | analytics_* | Analytics models |
| apps.payroll | payroll_* | PayrollEmployee, PayRun, etc. |

## Critical tables (identity + audit)

- **people_studentprofile** — Students (tenant-scoped).
- **people_teacherprofile** — Teachers.
- **people_studentguardian** — Guardian links.
- **audit_log** — TenantAuditLog; INSERT-only audit trail (see AUDIT_TRAIL_TRIGGER_BASED.md).

## How tables are created

1. **OnboardingService** ([apps/schools/onboarding_service.py](../apps/schools/onboarding_service.py)) creates Client + schema, then calls `_run_tenant_migrations(client)`.
2. **`_run_tenant_migrations`** runs `call_command("migrate", "--run-syncdb")` inside `tenant_context(client)`, so all TENANT_APPS migrations run in that schema.
3. No separate DDL script: Django migrations are the single source of truth. This doc is the **canonical reference** for what belongs in each tenant schema; add new tenant-scoped models to a TENANT_APP and add a migration.

## Adding a new tenant table

1. Add the model to an app listed in **TENANT_APPS** (config/settings.py when USE_DJANGO_TENANTS).
2. Run `python manage.py makemigrations <app>`.
3. Deploy: run `migrate_schemas --shared` then `migrate_schemas --tenant` (or migrate_tenant_schemas_one_by_one). New tenants get the table via onboarding; existing tenants get it when tenant migrations run.
