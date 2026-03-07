# Phase I Scale: Gap Analysis (Schema-Per-Tenant & Multi-Region)

This document is the **gap analysis** for Phase 4 (django-tenants migration) and Phase 5 (multi-region) from the Global Powerhouse Roadmap. Run `python manage.py phase_i_gap_analysis` to refresh checks.

---

## 1. Duplicate subdomains and slugs

**Requirement:** No two schools may share the same subdomain or slug (required for `schema_name` in django-tenants; schema names must be unique).

**Current schema:**
- `School.slug`: `SlugField(max_length=120, unique=True)` ✅
- `School.subdomain`: `CharField(max_length=120, unique=True, blank=True)` ✅

**Checks:**
- **Duplicate slug:** Database unique constraint enforces no duplicates. Migration to django-tenants must use slug (or a normalized form) as `schema_name`; PostgreSQL schema names have length and character restrictions (alphanumeric + underscore). Slug is already safe; subdomain can be empty.
- **Duplicate subdomain:** Unique constraint exists. If both slug and subdomain are set, they may differ (e.g. slug `ghs-limbe`, subdomain `ghs-limbe`); for schema_name we will use one canonical value (e.g. slug, falling back to subdomain or id).
- **Empty subdomain/slug:** At least one of slug or subdomain must be non-empty for every school. Run `phase_i_gap_analysis` to list any school with both empty (invalid for schema-per-tenant).

**Action:** Ensure every active school has a valid slug. Use slug as primary source for `schema_name` (sanitize: lowercase, replace `-` with `_` if needed for PostgreSQL).

---

## 2. Model partitioning: SHARED_APPS vs TENANT_APPS

**Principle:** In django-tenants, **SHARED_APPS** run in the public schema only; **TENANT_APPS** run in each tenant schema. Tenant models must not hold FKs to shared models that live in public (except via schema-aware connection). User can live in SHARED (one account, memberships per school) or in TENANT (separate logins per school). This codebase uses **one account, memberships per school** (SchoolMembership), so User stays in SHARED.

**Recommended partition:**

| App | Placement | Reason |
|-----|-----------|--------|
| `django.contrib.admin` | SHARED | Admin in public schema; can use TenantMainMiddleware to switch schema for admin per request if needed, or keep admin in public and list tenants from public. |
| `django.contrib.auth` | SHARED | User model shared. |
| `django.contrib.contenttypes` | SHARED | Content types in public. |
| `django.contrib.sessions` | SHARED | Sessions in public. |
| `django.contrib.messages` | SHARED | Messages in public. |
| `django.contrib.staticfiles` | SHARED | Static in public. |
| `unfold` | SHARED | Admin theme. |
| `django_otp`, `django_otp.plugins.*` | SHARED | MFA tied to User. |
| `rest_framework`, `rest_framework_simplejwt` | SHARED | API framework. |
| `apps.accounts` | SHARED | User, Role, permissions; no school FK on User. SchoolMembership links User to School (in public: School is in shared). |
| `apps.schools` | **SHARED** (partial) | School, SchoolMembership, SchoolProvisioningEvent, Domain (when added) live in **public**. Tenant-specific data (if any) would move to TENANT_APPS or stay shared with school_id. |
| `apps.siteconfig` | **SHARED** (partial) | RegionConfig, EducationSystemProfile, FeatureToggleDefinition, GlobalGeoCatalog, etc. in **public**. Models with school FK (e.g. FeatureToggleState, OfficialReportTemplate, Integration) can stay in SHARED and be filtered by school_id, or move to TENANT_APPS so they live in tenant schema. Plan: keep siteconfig in SHARED and filter by school_id (current pattern) unless we move tenant-scoped tables to tenant schema. |
| `apps.academics` | TENANT_APPS | All models have school FK; tenant data. |
| `apps.people` | TENANT_APPS | StudentProfile, TeacherProfile have school FK. |
| `apps.finance` | TENANT_APPS | FeePlan, Invoice, Payment have school FK. |
| `apps.evals` | TENANT_APPS | AssessmentWeights, TeacherAssignment, Evaluation have school FK. |
| `apps.reports` | TENANT_APPS | ReportCard has school FK. |
| `apps.communication` | TENANT_APPS | All communication models have school FK. |
| `apps.analytics` | SHARED or TENANT | If analytics are per-school, TENANT; if global only, SHARED. Current: check models for school FK. |
| `apps.payroll` | TENANT_APPS | If payroll has school FK; else SHARED. |
| `apps.compliance` | SHARED | Audit logs, IP country, etc. can be shared with tenant_id/school_id. |
| `apps.observability` | SHARED | Metrics in public. |
| `apps.api`, `apps.apicenter` | SHARED | API routing; apicenter may have school FK (per-tenant services) → move to TENANT if so. |
| `apps.automation` | SHARED or TENANT | Depends on models. |
| `apps.portal` | SHARED | Views only; data from other apps. |
| `apps.requests` | SHARED or TENANT | Depends on models. |
| `emis` | SHARED or TENANT | Depends on models. |
| `django_celery_results`, `django_celery_beat` | SHARED | Task results in public. |

**Summary list for settings.py (when USE_DJANGO_TENANTS=True):**

```python
SHARED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "unfold",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "rest_framework",
    "rest_framework_simplejwt",
    "apps.accounts",
    "apps.schools",   # School, SchoolMembership, Domain (Client in customers or here)
    "apps.siteconfig",
    "apps.compliance",
    "apps.observability",
    "apps.api",
    "apps.apicenter",
    "apps.portal",
    "apps.automation",
    "apps.requests",
    "emis",
    "django_celery_results",
    "django_celery_beat",
]
TENANT_APPS = [
    "apps.academics",
    "apps.people",
    "apps.finance",
    "apps.evals",
    "apps.reports",
    "apps.communication",
    "apps.analytics",  # if school-scoped
    "apps.payroll",   # if school-scoped
]
```

**Note:** `apps.schools` contains School (tenant identifier) and SchoolMembership; in django-tenants these stay in public. The **Client** (TenantMixin) can be a new model in `schools` or `customers` that holds `schema_name` and points to School or wraps it. Domain model links domain string to Client.

---

## 3. Foreign keys and uniqueness

**Rules:**
- **FK from tenant app to tenant app:** Allowed within same schema (tenant).
- **FK from tenant app to shared app:** Only to models that exist in **public** schema. In django-tenants, shared models are in public; tenant models are in tenant schema. So tenant models **cannot** have a direct FK to shared models (e.g. School) if School lives in public and tenant table in tenant schema—because FK would cross schema. **Solution:** Store `school_id` (UUID) as a non-FK column in tenant tables, or keep School in public and reference it by ID from tenant schema (django-tenants supports this with a custom approach: some projects store tenant_id only and resolve School in public). Standard approach: **Client (TenantMixin)** is in public; tenant tables have no FK to Client; they are in tenant schema and implicitly scoped by the schema. So we do **not** add School FK in tenant tables when data moves to tenant schema—the schema itself is the scope. Current codebase uses School FK everywhere; migration would: create tenant schema per school, copy rows into that schema, and **remove or replace** School FK with schema scope only. This is a large refactor. Alternative: keep single schema and keep School FK (current); Phase 4 is then optional and this gap analysis still applies when you decide to move.
- **Uniqueness:** Global uniques (e.g. slug in School) must be in SHARED. Per-tenant uniques (e.g. student_id within school) are valid in TENANT_APPS as unique together (tenant scope is implicit).

**Current tenant-scoped tables (with school FK):**  
See `TENANT_RLS_TABLES` in `apps/schools/management/commands/verify_tenant_rls.py`. All of these have a school FK today. For schema-per-tenant migration, each table would be copied into the tenant schema and the school_id column could be dropped (schema = tenant) or kept for reference if we still store school_id in public.

---

## 4. Phase 5: Multi-region readiness

**Tenant mapping:** Store each tenant’s **region** (e.g. region_id or country_code) in the shared schema (School or Client) so that:
- Regional S3: Route file storage to the bucket/location for that region (e.g. EU bucket for EU schools).
- CDN/edge: Route requests to the nearest regional endpoint.
- Data residency: Keep DB replicas or cells per region and route tenant to the correct cell.

**Actions:**
- Add `region_id` or `country_code` (or use existing `default_region_id` on School) for tenant → region mapping.
- Document regional S3 bucket strategy (e.g. `s3://bucket-eu/tenants/{school_id}/`, `s3://bucket-us/tenants/{school_id}/`).
- Document L10n pipeline (django-i18n + phrase/translation pipeline).
- Document regional payment gateways (M-Pesa, Pix, Stripe) and global MFA (already have django_otp).
- Latency-aware sync: Compression and edge routing (see roadmap Phase 5).

---

## 5. Migration script (when running Phase 4)

**Steps:**
1. Install django-tenants; add Client (TenantMixin) and Domain models; configure SHARED_APPS and TENANT_APPS.
2. For each School: create Client (schema_name=slug_normalized, name=school.name), create Domain(s) (subdomain + base domain, and custom_domain if set).
3. Run `migrate_schemas --shared` to create public schema and shared tables.
4. For each tenant: `with schema_context(schema_name): migrate_schemas --tenant` to create tenant schema; then copy data from public (academics, people, finance, evals, reports, communication) into tenant schema; then run sequence sync (sqlsequencereset or equivalent) to avoid PK collisions.
5. Switch middleware to TenantMainMiddleware; resolve request.tenant from Domain/subdomain; set connection to tenant schema.
6. Deploy: entrypoint runs `migrate_schemas --shared`, then `migrate_schemas --tenant` (or per-tenant), then **health check**, then Gunicorn.

---

## 6. Deploy health check

After migrations (or migrate_schemas), run a **lightweight health check** (e.g. one DB query) before starting Gunicorn so the orchestrator only routes traffic when the DB is ready. See `scripts/release/run_health_check.sh` and integration in render_predeploy and Docker entrypoint.
