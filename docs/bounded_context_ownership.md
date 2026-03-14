# Bounded Context Ownership

**Purpose:** §3.1 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Define owner per context and source-of-truth models. Nothing deferred.

**Status:** DONE — all 15 contexts defined with owner and source-of-truth.

---

## 1. Required bounded contexts

| Context | Owner (domain) | Source-of-truth models / surface |
|---------|----------------|----------------------------------|
| Identity & Access | accounts, config | User, SchoolMembership, credentials, MFA, SAML/OIDC, permission resolvers |
| People & Relationships | people | StudentProfile, TeacherProfile, GuardianProfile, relationships, identity resolution |
| Admissions | schools / admissions | Application, enrollment, admission number policy |
| Academics | academics | Course, Section, Term, Grade, evals, syllabus |
| Finance | finance | Invoice, Payment, Fee, ComplianceProfile, payment processors |
| Communications | communication | Announcement, messaging, channels, templates |
| Runtime & Metadata | platform_runtime, metadata | RuntimeDefaults, get_effective_site_settings, metadata catalog, resolvers |
| Marketplace | marketplace, packages | App, BlueprintPack, WorkflowPack, DashboardPack, PolicyBundle, install/rollback |
| Migration Cloud | automation, migration | MigrationRun, tenant provisioning, import/export |
| Analytics & Intelligence | analytics | Dashboards, reports, tenant maturity, health scores |
| Control Plane | schools (super), siteconfig (console) | Superadmin, tenant lifecycle, feature control, runtime inspector |
| Brand & Experience | brand_experience, siteconfig (theme) | ThemePack, branding, portal shell, experience packs |
| Plans & Entitlements | plans_entitlements | Plan, entitlement registry, capability checks |
| Global Registries & Localization | global_registries | RegionConfig, grading, locale, currency, education profile |
| Studio OS | studio_os, siteconfig (modes) | Experience Studio, Automation Studio, Output Studio, Launch Studio, Control Studio |

---

## 2. Approved cross-context interfaces

- **Tenant context:** Resolved per request by middleware/school; passed as `request.school` or `school_id`. No cross-context direct DB access to another context’s models without a defined API (e.g. runtime helpers, resolver functions).
- **Runtime:** All tenant-facing behavior reads through `platform_runtime.helpers` (get_effective_site_settings, get_effective_flags, get_platform_defaults) or context-specific resolvers (policies, registries, blueprints).
- **Settings:** No tenant app imports `siteconfig.models.SiteSettings` for behavioral reads; use runtime helpers only. See [SITECONFIG_FREEZE_POLICY.md](SITECONFIG_FREEZE_POLICY.md).
- **RLS context (schools):** `apps.schools.rls_context` is the single place for PostgreSQL `app.current_school_id` SET/RESET. Middleware and other callers use `set_rls_school_id(school_id)` and `reset_rls_school_id()`; no raw SQL in middleware. See [raw_sql_replacement_targets.md](raw_sql_replacement_targets.md). Contract tests: `apps.schools.tests.test_rls_context`.

---

## 3. CI enforcement

- **Scripts:** `lint_bounded_context_imports.py --strict`, `lint_siteconfig_legacy_imports.py` in `scripts/pre_deploy_gate.sh`.
- **Rule:** Forbidden cross-context imports are blocklisted; new imports must align with the table above.

---

## 4. Completion gate (§3.1)

- [x] Owner per context defined.
- [x] Source-of-truth models/surfaces documented per context.
- [x] Approved cross-context interfaces documented.
- [x] CI blocks forbidden cross-context imports.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §3.1.*
