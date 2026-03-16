# Schools app: school vs platform control-plane boundary

**Purpose:** §6.12 of the execution plan. Single place for the boundary between platform (super) and school/tenant (tenant) so routes and permissions stay consistent.

---

## 1. Boundary

| Plane | Host / path | Who | Views / entry | Permissions |
|-------|-------------|-----|----------------|-------------|
| **Platform control-plane** | Manager host (e.g. manager.runmycampus.com), `/super/`, `/admin/` | Superuser / staff with platform scope | super_views_*, admin, billing_dashboard, runtime_inspector, tenant catalog, create_school_wizard | is_staff, super-only views; no tenant RLS |
| **School / tenant** | Tenant host (subdomain or custom domain), tenant URL conf | Tenant staff, teachers, parents, students | Backend (tenant), portal, API per school | Tenant RLS; request.school; get_effective_site_settings(request) |

---

## 2. Rules

- **Super-only views:** Do not resolve or expose tenant data without explicit tenant scope (e.g. school_id in URL or session). Use platform DB or explicit tenant schema.
- **Tenant views:** Always run in tenant context (request.school, RLS). No direct SiteSettings.get_solo(); use get_effective_site_settings(request).
- **Public / AllowAny (schools):** SchoolConfigAPI (api_views) — host-resolved, read-only branding/flags; rate limiting and audit logging in place (public_endpoint_audit §6). No other public schools endpoints without audit.

---

## 3. Raw SQL (schools app)

All raw SQL in `apps/schools` is in repositories or rls_context (allowlist: raw_sql_audit.md). No ad-hoc raw SQL in app code. Health, RLS, tenant schema operations delegate to schools/repositories/*.

---

*Source: RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §6.12; public_endpoint_audit.md; raw_sql_audit.md.*
