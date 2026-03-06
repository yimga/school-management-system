# Phase 9 — Domain and Routing (Section 7)

Verification that public, superadmin, and tenant domains/hosts are implemented and documented, resolution order is documented and enforced, and separation in branding, IA, layout, and code is absolute.

---

## 7.1 — Public: runmycampus.com

| Requirement | Implementation |
|-------------|----------------|
| Marketing, demos, pricing, docs, signup, lead capture | **Host:** `public_host_kind(host)` returns `"base"` for base domain and `www.{base}`. `all_public_hosts()` includes canonical + legacy bases. |
| URLconf | **UrlConfSwitcherMiddleware:** when kind is `"base"`, `request.urlconf = config.public_urls`. Public shell: marketing, signup, discover, verify, support (no tenant data). |
| Code | `config/public_urls.py`; marketing views (e.g. `apps.schools.marketing_views`). |

---

## 7.2 — Superadmin: manager.runmycampus.com/super/

| Requirement | Implementation |
|-------------|----------------|
| Control plane only; tenant management, health, marketplace, support, policy/blueprint registry, rollout, migration control | **Host:** `public_host_kind(host)` returns `"manager"` for `manager.{base}`. |
| URLconf | When kind is `"manager"`, `request.urlconf = config.manager_urls`. Manager includes `super_urls` (e.g. `/super/`); super views require `require_super_access`; rate limit via SuperAdminRateLimitMiddleware. |
| Code | `config/manager_urls.py`, `apps/schools/super_urls.py`; control plane views only; no tenant app routes on manager host. |

---

## 7.3 — Tenant: portal.schoolname.com, schoolname.runmycampus.com

| Requirement | Implementation |
|-------------|----------------|
| School operations, branded experience, tenant-controlled dashboards and flows | **Host:** Tenant when host is not public (subdomain of base or custom domain). `public_host_kind(host)` returns `None` for tenant. |
| Resolution | RLS mode: `TenantMiddleware` resolves `request.school` from host (subdomain or custom domain or X-Tenant-Slug). Schema-per-tenant: `TenantMainMiddleware` resolves `request.tenant` (Client) from host; `TenantSchemaSchoolBridgeMiddleware` sets `request.school = tenant.school`. |
| URLconf | When tenant, `request.urlconf = config.tenant_urls`. Tenant shell: backend, portal, academics, finance, evals, reports, communication, etc. |
| Code | `config/tenant_urls.py`; tenant apps; branding/blueprint from `request.school` and policy. |

---

## 7.4 — Separation absolute in branding, IA, layout, navigation, code boundaries

| Aspect | Implementation |
|--------|----------------|
| Branding | Public: product branding. Manager: control-plane (dark, ops). Tenant: school-branded (School logo, colors; policy/blueprint). |
| IA | Public: marketing nav. Manager: command center, super nav. Tenant: role-based sidebar (portal_sidebar_items), dashboard hub, workflow hub. |
| Layout | Distinct templates/shells per urlconf (public, manager, tenant). |
| Code | No tenant app URLs on manager urlconf; no `/super/` on tenant urlconf — `ReservedPublicHostAccessMiddleware` redirects tenant host requests to `/super/` to manager host. |

**Reference:** phase2_control_tenant_shells.md, Section 24.7.

---

## 7.5 — Tenant resolution: subdomains, custom domains, exclusions, staging/preview, health

| Requirement | Implementation |
|-------------|----------------|
| Subdomains | Tenant resolved from `{slug}.{base}` when slug not in RESERVED_PUBLIC_SUBDOMAINS. |
| Custom domains | Domain model (django-tenants or custom) maps custom domain to tenant/school; resolver uses host. |
| Control-plane exclusions | www, admin, verify, support, api, docs, manager, developer never resolve to tenant. |
| Staging/preview | Path-based fallback `/t/<slug>/` optional via ALLOW_PATH_TENANT_FALLBACK in local/dev only (`allow_path_based_tenant_fallback`). |
| Health/internal routes | Health/ready endpoints on appropriate urlconf; internal routes not exposed on tenant UX. |

**Reference:** `apps/schools/host_routing.py` (RESERVED_PUBLIC_SUBDOMAINS, public_host_kind, is_public_host), tenancy.md (where tenant is set).

---

## 7.6 — Resolution order (documented and enforced)

**Order:** host → marketing/manager/tenant/custom → resolve tenant → set request tenant context → set DB schema context → load blueprint/policy → continue.

| Step | Implementation |
|------|----------------|
| 1. Host | Request arrives with host (and path). |
| 2. Type | `public_host_kind(host)` or equivalent: public (base, www, api, docs, …), manager, or tenant. |
| 3. Resolve tenant | If tenant: TenantMiddleware (RLS) or TenantMainMiddleware (schema-per-tenant) resolves School/Client from host, domain table, or X-Tenant-Slug. |
| 4. Request tenant context | `request.school` and/or `request.tenant` set; TenantContextMiddleware builds `request.tenant_ctx`. |
| 5. DB schema context | RLS: `set_config('app.current_school_id', …)`. Schema-per-tenant: connection.schema_name = tenant.schema_name. |
| 6. Load blueprint/policy | `get_effective_policy(school)`; context processor adds global_env, tenant_ctx. |
| 7. Continue | View/API runs with correct urlconf and tenant context. |

**Documentation:** `docs/architecture/request_flow_tenant_resolution.mmd` (Mermaid diagram). **Enforcement:** Middleware order in settings; UrlConfSwitcherMiddleware sets urlconf from host; tenant middleware sets school/tenant and schema/session vars.

**Reference:** tenancy.md, request_flow_tenant_resolution.mmd, config/settings.py (middleware order), apps/schools/middleware.py.

---

## Checklist summary

| Id | Status | Doc ref |
|----|--------|--------|
| 7.1 | Done | Public host + public_urls; host_routing, phase2. |
| 7.2 | Done | Manager host + manager_urls + super_urls; phase2. |
| 7.3 | Done | Tenant resolution + tenant_urls; tenancy.md. |
| 7.4 | Done | Phase2 separation; Section 24.7. |
| 7.5 | Done | host_routing, tenancy.md. |
| 7.6 | Done | request_flow_tenant_resolution.mmd; middleware order. |
