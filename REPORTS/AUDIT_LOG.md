# RunMyCampus Technical Audit Log

This artifact supports the deep-dive execution (Part 5 of the single plan). It is updated as audits and automated checks are run. **Isolation model:** schema-per-tenant (PostgreSQL schema per school); do not rely on `tenant_id` or RLS for isolation.

---

## 1. Queries missing schema scope

- **Definition:** Any tenant-scoped database query that does not run in the correct tenant schema (e.g. missing or wrong `search_path`/schema context), or any shared-app code that accesses tenant data without setting schema.
- **Status:** Audited (codebase scan). Tenant context is used where tenant data is touched from shared apps.
- **Findings:**

| Location | Issue | Action |
|----------|--------|--------|
| apps/schools/tasks.py | Uses `tenant_context(client)` for tenant-scoped provisioning | OK |
| apps/schools/onboarding_service.py | Runs migrations and seed inside tenant_context | OK |
| apps/siteconfig/import_ui_config.py | Iterates Clients and uses tenant_context per client | OK |
| apps/schools/migrate_tenant_schemas_one_by_one.py | Uses tenant_context for each Client | OK |
| _Ongoing_ | Any new shared-app code that queries tenant tables must use `tenant_context(client)` or equivalent | Enforce in review |

---

## 2. Hardcoded strings (i18n)

- **Definition:** Visible strings that are not using the i18n translation library (gettext/trans).
- **Status:** Partial. Many modules use gettext (`_()`, `gettext_lazy`); coverage varies by app.
- **Findings:**

| Location | String / Snippet | Action |
|----------|-------------------|--------|
| apps/portal, apps/finance, apps/people | Multiple user-facing strings use `_()` or `gettext_lazy` | OK where present |
| apps/schools/marketing_views.py | Marketing copy in MARKETING_PAGE_DEFINITIONS | Consider i18n for multi-locale marketing |
| Admin/templates | Some labels and messages | Add trans tags where missing |
| _General_ | Complete gettext pass per blueprint | Run extract/compile; fill gaps in high-traffic views |

---

## 3. API endpoints without rate limiting

- **Definition:** API views or endpoints that lack throttle/rate_limit.
- **Status:** Audited. Key auth and public endpoints use throttle; DRF views may use throttle_classes.
- **Findings:**

| Endpoint / View | Action |
|-----------------|--------|
| apps/api/auth_views.py | RateLimitedTokenObtainPairView, RateLimitedTokenRefreshView — OK |
| apps/api/rate_limit.py | throttle_ip_request used in auth, SCIM, section8, ministry_placeholders |
| apps/api/mobile_api.py | MobileRateThrottle, MobileAnonRateThrottle on mobile endpoints — OK |
| apps/schools/section8_views.py | throttle_ip_request on discovery/find — OK |
| Other APIView subclasses | Ensure throttle_classes or throttle_ip_request where appropriate | Add where missing |

---

## 4. Background scripts/jobs (idempotency, error handling, tenant context)

- **Definition:** Celery tasks and management commands; for each: idempotency, error handling, and tenant/schema context.
- **Status:** Listed. Full inventory in ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.
- **List:**

| Script / Task | Idempotent | Error handling | Tenant/schema context | Notes |
|---------------|------------|----------------|------------------------|--------|
| provision_school_task (schools/tasks) | Yes (skip if active) | Events on failure | tenant_context(client) | OK |
| siteconfig.* (calculate_monthly_revenue_stats, send_welcome_email, etc.) | Varies | Retry where bind=True | Pass school_id where needed | Review per task |
| finance.* (send_payment_reminders, auto_generate_fee_invoices, etc.) | dry_run / idempotent patterns | autoretry_for on some | Tenant-scoped by schema | OK |
| migrate_tenant_schemas_one_by_one | Yes | Log and continue | tenant_context per Client | OK |
| seed_global_regions, verify_region_coverage | Yes | Exit on error | Public schema | OK |
| All management commands (100+) | Varies | Document per command | Use tenant_context if touching tenant tables | See apps/*/management/commands/ |

---

## 5. Security scan results

- **Definition:** Output of SonarQube, Snyk, or similar; and any manual security review.
- **Status:** _To be filled when CI/security scans are run._
- **Findings:**

| Tool | Date | Summary / Link |
|------|------|-----------------|
| (CI) | — | Add SonarQube or Snyk to CI; paste summary/link when run. |
| Manual | — | Run `python manage.py check --deploy`; security checklist in docs/SECURITY_IMPLEMENTATION_GUIDE.md. |

---

## 6. Accessibility (WCAG) and mobile

- **Definition:** Gaps found via pa11y, Lighthouse, or manual review; mobile responsiveness.
- **Status:** Partial. Tests in apps/siteconfig/tests/test_accessibility.py; marketing uses responsive layout.
- **Findings:**

| Page / Component | Issue | Action |
|------------------|--------|--------|
| Marketing landing | Responsive (landing-stack, clamp); check contrast | Run pa11y/Lighthouse; fix contrast if needed |
| Portal / backend | Theme and high-contrast options in user preferences | Document in ACCESSIBILITY.md |
| _General_ | Run `python manage.py check_accessibility` or pa11y on key URLs | Add to CI; record failures here |

---

## 7. Clean Architecture & SOLID

- **Definition:** Violations of domain/application/infrastructure separation, dependency rule, or SOLID principles.
- **Status:** Noted. Services and views mix some concerns; no strict layer enforcement.
- **Findings:**

| Location | Violation | Action |
|----------|-----------|--------|
| apps/*/views*.py | Views sometimes contain business logic | Extract to service layer where complex |
| apps/*/models.py | Models may reference cross-app FKs | Acceptable; document boundaries |
| apps/siteconfig, apps/schools | Provisioning and config in multiple modules | Consolidate where it improves clarity |
| _General_ | No formal domain/application/infrastructure folders | Consider for new features; refactor incrementally |

---

## 8. Day 1 / Master architecture

- **Doc:** [docs/DAY1_MASTER_ARCHITECTURE.md](../docs/DAY1_MASTER_ARCHITECTURE.md) — three-layer shield (Global Gateway, Tenant Fortress, Intelligence Mesh) and Day 1 checklist (Master Control, Tenant Provisioner, schema-aware middleware, Security Sentinel, Command Center UI).

---

## 9. Checklist (from existing docs) and plan completion

- **Plan completion:** [docs/PLAN_COMPLETION_CHECKLIST.md](../docs/PLAN_COMPLETION_CHECKLIST.md) — single checklist for RUNMYCAMPUS_SINGLE_PLAN_COMPLETE (Part 0–5, 4.4–4.11, optional items).

- **THREE_PLANS_EXECUTION_GUIDE:** Execution order; use as checklist for phased rollout.
- **KEY_MODULES_REFERENCE:** Module map; cross-check FEATURE_GATE_PATH_MAP and feature registry.
- **ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS:** List Celery tasks and management commands; document idempotency and tenant context.
- **MODULE_AUDIT_AND_IMPROVEMENT_PLAN:** Per-module audit items; add findings to sections 1–7 above.
- **Blueprint alignment:** Per RUNMYCAMPUS_SINGLE_PLAN_COMPLETE: mark each major area as In plan / In roadmap / Not yet.

---

## 10. Marketing / public site (everything inventory)

- **Views:** [apps/schools/marketing_views.py](../apps/schools/marketing_views.py) — marketing_page, MARKETING_PAGE_DEFINITIONS (home, about, features, blog, contact, pricing, etc.).
- **Templates:** marketing_landing.html, marketing_page.html; nav derived from definitions.
- **Routes:** [config/public_urls.py](../config/public_urls.py). Check i18n and WCAG on marketing pages; record gaps in section 6.

---

## 11. Audit trail (Part 4.6) — trigger-based, PII masking

- **Table:** `audit_log` (TenantAuditLog) per tenant schema; migration `0036_add_tenant_audit_log`.
- **Triggers:** Migration `0037_audit_triggers_tenant_schema` attaches to `people_studentprofile` and `people_teacherprofile` in each tenant schema. Same trigger can be attached to other tables via `python manage.py attach_audit_triggers --tables <table1> <table2>`.
- **Immutable audit_log:** Run `python manage.py revoke_audit_log_permissions` after tenant migrations to REVOKE UPDATE/DELETE on audit_log per schema.
- **PII masking:** Trigger strips these keys from `old_values`/`new_values` before insert: `password`, `password_hash`, `secret`, `token`, `api_key`, `card_last4`, `card_number`, `ssn`, `social_security`. Extend in `0037` `REDACT_KEYS` or in the command. Never log full PII; add table-specific redaction if needed.
- **Doc:** [docs/AUDIT_TRAIL_TRIGGER_BASED.md](../docs/AUDIT_TRAIL_TRIGGER_BASED.md).

---

## 12. Optional: RLS, PgBouncer, retention, alerts, module map

- **RLS (defense-in-depth):** See [docs/OPTIONAL_DEPLOYMENT_AND_AUDIT.md](../docs/OPTIONAL_DEPLOYMENT_AND_AUDIT.md) §1. Enable RLS on tenant tables only if desired; schema is primary isolation.
- **PgBouncer:** Connection pooling for multi-schema; see same doc §2. Document in deployment guide when scaling.
- **Audit retention / cold storage:** Retention policy and archive-to-S3 (or similar) for `audit_log`; see same doc §3 and [docs/AUDIT_TRAIL_TRIGGER_BASED.md](../docs/AUDIT_TRAIL_TRIGGER_BASED.md).
- **Real-time alerts:** Optional webhook on SiteSettings change — set `GLOBAL_CHANGE_ALERT_WEBHOOK_URL`; see [OPTIONAL_DEPLOYMENT_AND_AUDIT.md](../docs/OPTIONAL_DEPLOYMENT_AND_AUDIT.md) §4 and siteconfig.models `_emit_global_change_alert`.
- **Module/workflow map:** [docs/MODULE_WORKFLOW_MAP.md](../docs/MODULE_WORKFLOW_MAP.md).

---

## Changelog

| Date | Author | Change |
|------|--------|--------|
| (today) | Plan execution | Initial structure created (Part 5 step 1). |
| (today) | Plan execution | Added Day 1 doc link, checklist, marketing inventory (steps 7–8). |
| (today) | Plan execution | Section 11: audit trail triggers + PII masking; Section 12: optional RLS, PgBouncer, retention, alerts, module map. |
