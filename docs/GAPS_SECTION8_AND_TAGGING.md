# Gaps: Section 8 (Industry Interoperability) & Information Tagging

This document lists **gaps and missing pieces** identified across **committed** and **staged/unstaged** code for the work done on Section 8, Section 9, and the Information Tagging system. Use it for pre-merge checks and follow-up.

---

## Git state (reference)

- **Committed:** Latest commit is multi-tenant profile governance / provisioning / global config.
- **Unstaged / untracked:** All Section 8, Section 9, and Information Tagging work (views, models, migrations, templates, docs) is in the working tree and/or untracked. **Nothing from this work is staged yet.**

---

## Fixes applied in this pass

| Gap | Fix |
|-----|-----|
| **Tag Manager RBAC** | Tag Manager and Tag Manager Edit now use `@permission_required("settings.manage")` so only users with settings.manage (e.g. Admin/Leadership) can access; aligned with Customizer and Report Library. |
| **SSL redirect exemptions** | Added `api/caddy-check/`, `discover/`, and `account-frozen/` to `SECURE_REDIRECT_EXEMPT` so Caddy, discovery landing, and frozen page can be reached over HTTP where needed (e.g. Caddy ask, health probes). |
| **Caddy IP allowlist** | When `CADDY_CHECK_ALLOWED_IPS` (comma-separated) is set, only those IPs get 200/404 from `/api/caddy-check/`; others get 403. Documented in DEPLOY_CHECKLIST. |
| **Discovery rate limiting** | POST to `/discover/` is rate limited: max 10 requests per IP per 15 minutes (cache-based). When exceeded, response is 429 with “Too many attempts.” |
| **Section 8 tests** | `apps.schools.tests.test_section8_views`: Caddy (domain, localhost, custom verified/unverified, IP allowlist), discovery (GET form, POST redirect/error, rate limit 429), LTI placeholder (501/404), frozen view, TenantFreezeMiddleware (redirect, exempt path, staff bypass). |
| **Information Tagging tests** | `apps.people.tests.test_information_tag`: InformationTag model (create, unique school+name, str), student tags + nuance “in” operator, critical-tag signal creating AccessRequest. |

---

## Gaps still open (recommended follow-up)

### 1. Tests

- **Section 8** — Addressed: `apps.schools.tests.test_section8_views` (Caddy, discovery, LTI placeholder, frozen view, TenantFreezeMiddleware, Caddy IP allowlist, discovery rate limit 429).
- **Information Tagging** — Addressed: `apps.people.tests.test_information_tag` (InformationTag model, StudentProfile.tags, nuance “in” + student_tags, critical-tag → AccessRequest).

---

### 2. Security & hardening

- **Caddy endpoint** — Addressed: when `CADDY_CHECK_ALLOWED_IPS` is set, only those IPs are allowed; others get 403.

- **Global login discovery** — Addressed: rate limiting (10 POSTs per IP per 15 min, 429 when exceeded). “Get started” still links to `super:create_school_wizard`; confirm if unauthenticated users should see that or a different landing.

- **Tag Manager**  
  Now gated by `settings.manage`; no further gaps.

---

### 3. Powerhouse / Request-to-Feature (tenant hooks)

- **Implemented:** Canonical hook registry (`apps.siteconfig.hooks`), `{% tenant_hook %}` placed in student list, student 360, gradebook, finance dashboard; Request custom requirement page (`/siteconfig/request-custom-requirement/`); sidebar link for users with `settings.manage`. See **docs/TENANT_HOOKS.md**.

### 4. Plan / audit docs

- **PLAN_VERIFICATION_AUDIT.md**  
  Does not yet include:
  - **Section 8** (Industry Interoperability): Caddy ask, discover, LTI placeholder, JWKS, frozen account, TenantFreezeMiddleware, health utils, support dashboard health block, ServiceIntegration/WebhookSubscription admin).
  - **Information Tagging**: InformationTag model, StudentProfile.tags, Tag Manager UI, nuance `student_tags` + `in`, critical-tag → AccessRequest, docs/INFORMATION_TAGGING.md.

**Recommendation:** Add a “Section 8” and an “Information Tagging” subsection to the audit with a small status table and tick items as done.

---

### 5. Edge cases and behavior

- **global_login_discovery**  
  When the user’s school has no `subdomain`, the code redirects to `accounts:login` with `?next=/portal/`. On the main domain, `request.school` may be null; login redirect behavior is fine, but “school context after login” depends on session or school picker. No code bug; just something to be aware of.

- **Frozen page**  
  Uses `request.user` in the template (e.g. staff bypass link). With the auth context processor, `request.user` is always set (AnonymousUser when not logged in). No 500 risk.

- **Health utils**  
  `get_top_tables_by_size` and `get_global_health_stats` are PostgreSQL-only (return `[]` on other backends). Super dashboard Health block is hidden when list is empty. No gap.

- **AccessRequest for critical tag**  
  Uses `ContentType` and `target_object_id` for the student. Requests dashboard does not filter by school (AccessRequest has no `school_id`). If you need per-school request lists, you’d add a school field or derive school from target (student → school). Document as a known limitation or future improvement.

---

### 5. Migrations and deploy

- **Migration order**  
  New migrations (e.g. people 0029, siteconfig 0102, schools 0011) have dependencies set. Run `python manage.py migrate` (or `migrate_schemas` if using django-tenants) and confirm order in DEPLOY_CHECKLIST.

- **Untracked migrations**  
  Several migrations are untracked (people 0029, siteconfig 0102, schools 0011, etc.). Ensure they are committed with the feature so deployments don’t miss them.

---

### 7. Optional improvements

- **LTI / webhooks**  
  Section 8 has placeholders (LTI 501, JWKS empty). When implementing for real, follow DEPLOY_CHECKLIST “Integration security checklist” (no secrets in logs, HMAC for webhooks, scoped tokens, tenant_id, audit).

- **Information Tagging**  
  - **System tags:** INFORMATION_TAGGING.md mentions optional global “system tags” (e.g. Active, Graduated) with `school_id` null; not implemented.
  - **Student profile edit in backend:** Tags are editable in Django Admin and list shows pills; a dedicated “Edit student” backend page could expose tag assignment without going through Admin.

---

## Summary

- **Fixed in this pass:** Tag Manager permission (`settings.manage`), SECURE_REDIRECT_EXEMPT for Caddy, discover, and account-frozen.
- **Still missing:** Tests for Section 8 and Information Tagging; rate limiting on discovery; optional Caddy IP allowlist; Section 8 and Tagging entries in PLAN_VERIFICATION_AUDIT; optional per-school filtering for critical-tag AccessRequests.
- **Safe to merge from a consistency standpoint:** Yes, after running `check --deploy`, relevant tests, and ensuring all new migrations are committed and run in order.
