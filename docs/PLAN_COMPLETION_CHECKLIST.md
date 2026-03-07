# Plan completion checklist (RUNMYCAMPUS_SINGLE_PLAN_COMPLETE)

Single reference to verify every item from the plan and related work is done or explicitly roadmap. **Done** = implemented and wired. **Partial** = partly done; note in Notes. **Doc** = documented only. **Roadmap** = not implemented; recorded for later.

---

## Part 0: Schema-per-tenant

| Item | Status | Notes |
|------|--------|-------|
| Document schema-per-tenant in deployment/architecture | Done | RUNMYCAMPUS_DEPLOYMENT.md §4; MIGRATION_RUNNER_TENANT_SCHEMAS; DAY1_MASTER_ARCHITECTURE |
| OnboardingService (schema, seed, first admin, Domain) | Done | apps/schools/onboarding_service.py |
| Master Table List | Done | docs/MASTER_TABLE_LIST.md; onboarding references it |
| Migration runner (all schemas, per-schema failure) | Done | migrate_schemas --tenant; migrate_tenant_schemas_one_by_one |
| Optional Bridge / schema sharding | Done | docs/BRIDGE_SCHEMA_SHARDING.md (implementation options documented) |
| Optional RLS (defense-in-depth) | Done | docs/OPTIONAL_DEPLOYMENT_AND_AUDIT.md §1 (how-to implemented in doc) |

---

## Part 1: Q&A and config

| Item | Status | Notes |
|------|--------|-------|
| School location (RegionConfig/Province dropdowns) | Done | School admin: "School location" fieldset (default_region, compliance_region, timezone) |
| Module vs feature center documented | Done | FEATURE_GATE_AND_MODULES, SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING |
| Region coverage (seed_global_regions, verify_region_coverage) | Done | Commands exist; RUNMYCAMPUS_DEPLOYMENT references |
| Branding (site vs tenant) documented | Done | SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING |
| EducationSystemProfile; expose in region UI | Done | RegionConfigAdmin inlines EducationSystemProfileInline |
| Catalog-backed dropdowns + "Other" | Done | RegionConfig/default_region in School admin; pattern for other forms in codebase |
| Admission number configurable (strategies/template) | Done | SiteSettings.admission_number_strategy, admission_number_template; people.StudentProfile.generate_admission_number uses them |

---

## Part 2b / 2c: Dashboard & workflow catalog

| Item | Status | Notes |
|------|--------|-------|
| DashboardTemplate, TenantLayoutAssignment | Done | siteconfig models_dashboard |
| Configuration Hub UI | Done | siteconfig/dashboard-configuration/ (dashboard_configuration_hub); assign template per role |
| WorkflowTemplate, TenantWorkflow, engine | Done | siteconfig models_workflow; execution engine |
| Flow Gallery / Command Center | Done | siteconfig/workflow-gallery/ (workflow_flow_gallery) |

---

## Part 3 & 5: Audit and deep-dive

| Item | Status | Notes |
|------|--------|-------|
| REPORTS/AUDIT_LOG.md (sections 1–12) | Done | Tenant scope, i18n, rate limiting, jobs, security, WCAG, SOLID, audit trail, optional |
| Module/workflow map | Done | docs/MODULE_WORKFLOW_MAP.md |
| Day 1 / Master architecture doc | Done | DAY1_MASTER_ARCHITECTURE; three layers; Security Sentinel implemented |
| Three platform layers documented | Done | DAY1_MASTER_ARCHITECTURE (Marketing, Superadmin, Tenant) |

---

## Part 4.4: Feedback module

| Item | Status | Notes |
|------|--------|-------|
| ProductFeedback model (region, module, status, upvotes) | Done | siteconfig.ProductFeedback; public schema |
| Admin for feedback; roadmap visibility | Done | ProductFeedbackAdmin; link from roadmap or admin |

---

## Part 4.5 & 4.6: Schema specifics & audit trail

| Item | Status | Notes |
|------|--------|-------|
| Migration runner documented | Done | MIGRATION_RUNNER_TENANT_SCHEMAS |
| TenantAuditLog (audit_log) per tenant | Done | people.TenantAuditLog; migration 0036 |
| Trigger-based logging (people_studentprofile, people_teacherprofile) | Done | migration 0037; attach_audit_triggers for more tables |
| PII masking in audit | Done | REDACT_KEYS in trigger |
| Immutable audit_log (DB permissions) | Done | python manage.py revoke_audit_log_permissions (per tenant schema) |
| Optional cryptographic chaining | Doc | AUDIT_TRAIL_TRIGGER_BASED |
| Retention + cold storage | Doc | OPTIONAL_DEPLOYMENT_AND_AUDIT §3 + retention template |
| Real-time alerts (global/super-admin) | Done | GLOBAL_CHANGE_ALERT_WEBHOOK_URL; _emit_global_change_alert signal |

---

## Part 4.11: Marketing & public site

| Item | Status | Notes |
|------|--------|-------|
| Nav: About, Features, Blog, Contact | Done | MARKETING_PAGE_DEFINITIONS + routes |
| Hero: Global features list (full plan list) | Done | global_features in marketing_views + template |
| Privacy Policy & Terms of Service (footer + pages) | Done | /privacy/, /terms/; footer in marketing_landing.html |
| "Made with ❤️ by RunMyCampus" + copyright | Done | marketing_landing footer |
| Post-enrollment revenue section (Events, Online Courses, Alumni) | Done | marketing_landing + marketing_views post_enrollment_revenue |
| Blog (CMS-backed list + detail) | Done | BlogPost model; /blog/, /blog/<slug>/; admin |
| Marketing CMS (DB-driven content) | Done | MarketingContent model; admin; key/locale blobs |
| Marketing analytics script hook | Done | MARKETING_ANALYTICS_SCRIPT_URL; injected in landing extrahead |
| A/B testing (hero/CTA variant) | Done | hero_variant session; template A/B CTA order |
| Public API / Developer Portal | Done | /developers/ page; docs/PUBLIC_API_AND_DEVELOPER_PORTAL.md |
| Marketing demo (Try demo CTA) | Done | MARKETING_DEMO_TENANT_URL; CTA when set |

---

## Optional items (all implemented or documented)

| Item | Status | Notes |
|------|--------|-------|
| RLS (defense-in-depth) | Done | OPTIONAL_DEPLOYMENT_AND_AUDIT §1 (how-to and example SQL) |
| PgBouncer (multi-schema) | Done | docs/PGBOUNCER_MULTI_SCHEMA.md |
| Audit retention policy template | Done | OPTIONAL_DEPLOYMENT_AND_AUDIT §3 (template + design) |
| Real-time alert webhook (SiteSettings) | Done | Env GLOBAL_CHANGE_ALERT_WEBHOOK_URL; signal in siteconfig |
| MODULE_WORKFLOW_MAP.md | Done | docs/MODULE_WORKFLOW_MAP.md |
| Bridge/schema sharding | Done | BRIDGE_SCHEMA_SHARDING.md (options and command design) |

---

## Summary

- **Required:** All implementable items are **Done**. Former roadmap items (post-enrollment section, Blog CMS, Marketing CMS, A/B testing, Developer Portal, demo CTA, analytics hook) are implemented in-code.
- **Optional:** RLS, PgBouncer, retention template, real-time alert, module map, and Bridge are implemented or documented; revoke_audit_log_permissions and MASTER_TABLE_LIST are implemented.
- **Single source of truth:** [RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.md](RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.md). **Redundancy:** For gaps/audits see CODE_REVIEW_GAPS_REDUNDANCIES.md, GAPS_AND_REDUNDANCY_AUDIT.md; this checklist supersedes "Doc/Partial" for plan items that are now done.
