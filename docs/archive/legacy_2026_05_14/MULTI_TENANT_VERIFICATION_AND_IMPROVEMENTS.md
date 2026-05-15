# Multi-Tenant Verification and Completeness Checklist

This document maps the real-world multi-tenant requirements (data isolation, provisioning, feature toggles, regional flexibility, Super Admin, usage monitoring) to the current codebase and notes what is complete and what is optional or future.

---

## 1. Data Isolation Strategy

| Requirement | Status | Location |
|-------------|--------|----------|
| **Shared DB, row-level isolation** | Done | All tenant-scoped models have `school` FK (or are reachable via school-scoped relations). |
| **school_id on tenant tables** | Done | `apps/schools/models.py` (School); people, academics, finance, evals, reports, siteconfig use `school = ForeignKey("schools.School", ...)`. |
| **PostgreSQL RLS** | Done | `apps/schools/middleware.py` sets `app.current_school_id`; `apps/schools/migrations/0002_enable_rls_postgresql.py` and verify command: `python manage.py verify_tenant_rls`. |
| **RLS on all tenant tables** | Done | `apps/schools/management/commands/verify_tenant_rls.py` lists TENANT_RLS_TABLES (schools_schoolmembership, people_*, academics_*, finance_*, evals_*, reports_*, siteconfig_officialreporttemplate). |
| **Single-tenant fallback** | Done | `SINGLE_TENANT` env or single active school: middleware resolves to that school when no subdomain. |

**Note:** `academics.Incident` has no direct `school` FK; it is scoped via `student.school` / `teacher.school`. For strict RLS and discipline module multi-tenant consistency, consider adding `school = ForeignKey(School, null=True, ...)` to Incident and setting it from student/teacher on save (and add to TENANT_RLS_TABLES if using RLS).

---

## 2. Tenant-Aware Authentication and Resolution

| Requirement | Status | Location |
|-------------|--------|----------|
| **Subdomain resolution** | Done | `TenantMiddleware`: extracts subdomain from host, looks up `School` by `subdomain` or `slug`. |
| **Custom domain (whitelabel)** | Done | `School.custom_domain`, `custom_domain_verified`; middleware checks host against `custom_domain` first. `get_cname_target()` for CNAME hint. |
| **Session school_id** | Done | `request.session['school_id']` set when school resolved. |
| **User–school mapping** | Done | `SchoolMembership`: user, school, role, is_primary. Users can belong to multiple schools. |
| **Login / JWT** | Partial | Login is global; tenant is determined by **host** (subdomain/custom domain) or session. No JWT school_id in token; backend uses `request.school` from middleware. |

---

## 3. Super Admin Dashboard and Provisioning

| Requirement | Status | Location |
|-------------|--------|----------|
| **Super Admin UI** | Done | `/super/` dashboard; access: SUPERADMIN or is_superuser; gated by `enable_super_admin_ui` in Feature Control. |
| **“Create School” button** | Done | `templates/schools/super_dashboard.html` → `Create School` → wizard. |
| **Step-by-step wizard** | Done | Steps: 1 Identity (name, slug, subdomain, contact email), 2 Region (region_code, sub_system), 3 Branding (primary_color, accent_color). Optional Step 4 Domain (custom_domain) added. |
| **API create school** | Done | `POST /super/api/create-school/` creates School (is_active=False), enqueues provisioning. |
| **Provisioning task** | Done | `apps/schools/tasks.py`: `provision_school_sync` creates admin user (or links by email), SchoolMembership, AcademicYear, Terms, optional default Subjects; sets `is_active=True`. |
| **Usage monitoring (billing)** | Done | Super dashboard table shows per-school: Students, Teachers, Members (counts). |
| **Subscription / feature limits** | Per-school | Use `School.features` (Module Market) to enable/disable modules per school; no built-in “plan” or billing yet. |

---

## 4. Modular School-Specific Settings and Feature Toggles

| Requirement | Status | Location |
|-------------|--------|----------|
| **Configuration table** | Done | `School.settings` (JSON): grading_logic, term_count, custom fields, etc. `School.default_region` for currency, timezone, grading scale. |
| **Feature toggles per school** | Done | `School.features` (JSON): e.g. `{"library": true, "transport": false, "offline_mode": true}`. `school.has_feature(code)`. |
| **Module Market (App Store)** | Done | `siteconfig:module_market` – list available modules, activate/deactivate for **current school**; updates `School.features`. |
| **Dynamic branding** | Done | Context: `SITE_LOGO_URL`, `SITE_PRIMARY_COLOR`, `SITE_ACCENT_COLOR` from `request.school` when set. Templates (portal_base, base, reports) use CSS variables and logo URL. |
| **No hard-coded school name** | Done | Site name and branding come from SiteSettings (single-tenant) or School (multi-tenant). |

---

## 5. Regional and Bilingual Flexibility (Cameroon and Beyond)

| Requirement | Status | Location |
|-------------|--------|----------|
| **Sub-system (FR/EN/INT)** | Done | `School.sub_system` (French sub-system, English sub-system, International). |
| **Region per school** | Done | `School.default_region` → RegionConfig (currency, timezone, grading_scale, term_count, etc.). |
| **i18n / bilingual** | Done | Django i18n; `region_settings` context uses school’s region for default_language and grading; report styles and CertificateLocalizer support multiple languages. |
| **Grading engine flexibility** | Done | Region and School.settings drive grading scale (e.g. coefficient vs A–E); report card styles and presets. |
| **Timezone** | Done | `School.timezone` (e.g. Africa/Douala); stored UTC in DB, converted at view layer. |

---

## 6. Compliance and Security

| Requirement | Status | Location |
|-------------|--------|----------|
| **Data residency** | Configurable | Single deployment; data residency is by deployment region. No per-school DB location in code. |
| **Encryption in transit** | Deployment | HTTPS at reverse proxy / load balancer. |
| **Encryption at rest** | Deployment | Database and storage encryption are infrastructure concerns. |
| **RLS enforcement** | Done | PostgreSQL RLS ensures tenant isolation when `app.current_school_id` is set. |

---

## 7. Optional / Future Improvements (from your notes)

| Improvement | Status | Notes |
|-------------|--------|--------|
| **Logo upload in wizard** | After creation | Wizard says “Logo upload can be done after creation in school settings.” Logo can be set via Admin → School → logo_url or a future school settings upload. |
| **Wildcard DNS** | Deployment | Configure `*.yoursystem.com` → server IP; no code change. |
| **Custom domain API (Cloudflare/Route 53)** | Not implemented | School stores `custom_domain`; CNAME/SSL is manual or future integration. |
| **Mobile Money (MoMo) per school** | Not implemented | Finance can be extended with tenant-specific payment merchant IDs. |
| **Super-tenant (parent school)** | Done | `School.parent_school`; `parent_tenant_views` for consolidated dashboard. |
| **Offline-first / PWA** | Done | Global flag + per-school `offline_mode` in Module Market. |
| **Official report templates (MINESEC)** | Done | Report card styles and templates; region-specific. |

---

## 8. Verification Commands

- **RLS (PostgreSQL):** `python manage.py verify_tenant_rls`
- **Create new school:** Log in as SUPERADMIN → Schools → Create School → complete wizard → POST to `/super/api/create-school/`
- **Module Market:** In a school context (subdomain or selected school), go to Settings → Module Market (or `siteconfig:module_market`)

---

## 9. Summary

The codebase already implements:

- **Data isolation:** Shared DB with `school_id` and PostgreSQL RLS; TenantMiddleware and session.
- **Provisioning:** Super Admin dashboard, Create School wizard (Identity, Region, Branding, Domain), API, and synchronous provisioning task (admin user, membership, terms, subjects).
- **Feature toggles:** Global (Feature Control) and per-school (School.features + Module Market).
- **Dynamic branding:** Logo and primary/accent colors from `request.school` in context and templates.
- **Regional/bilingual:** Sub-system, default_region, timezone, i18n, flexible grading.
- **Usage monitoring:** Super dashboard shows student and teacher counts per school.

Improvements made in this pass:

- **Wizard:** Optional Step 4 “Domain” with custom domain field and CNAME hint.
- **Success message:** Link to “Edit school” (Admin) after creation so admin can set logo and custom domain.

For **discipline module** multi-tenant consistency, consider adding `school` FK to `Incident` (and any new discipline models) and including them in RLS verification.
