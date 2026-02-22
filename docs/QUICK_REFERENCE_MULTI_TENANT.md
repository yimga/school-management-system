# Multi-Tenant Admin & URLs — Quick Reference

One-page reference for **Main (Public) Admin**, **Tenant Admin (Backend)**, and **tenant-specific URLs**. Full details: [MULTI_TENANT_ADMIN_AND_URLS.md](MULTI_TENANT_ADMIN_AND_URLS.md), [RENDER_URL_MAPPING_PLAN.md](RENDER_URL_MAPPING_PLAN.md).

**Rule:** **Main Admin = base domain only.** **Tenant pages = not at root on base domain** — use **path-based `/t/<school_slug>/`** (Option A) or subdomain/custom domain (Option B).

---

## URLs (Render: `https://school-management-system-2kzk.onrender.com`)

| Purpose | URL | Who |
|--------|-----|-----|
| **Main (public) admin** | **Base domain only:** `https://school-management-system-2kzk.onrender.com/admin/` | Superuser only |
| **Super Admin** | **Base domain only:** `https://school-management-system-2kzk.onrender.com/super/` | Superuser (provisioning) |
| **Tenant Backend** | **Subdomain only:** `https://gilead-school.school-management-system-2kzk.onrender.com/authentication/backend/` | Staff/users for that school |
| **Login** | Base domain: `/authentication/login/` (then redirect to tenant subdomain if user has a school) | All users |
| **Discover** | Base domain: `/discover/` | Public → tenant login |

**Local:** Set `MULTI_TENANT_BASE_DOMAIN=localhost`. Main admin = `http://localhost:8000/admin/`; Tenant = `http://gilead-school.localhost:8000/authentication/backend/`.

---

## Canonical tenant URLs (all on tenant subdomain or custom domain)

These paths are the main entry points for each tenant. They all resolve on the tenant host (e.g. `https://gilead-school.school-management-system-2kzk.onrender.com/...`).

| Purpose | Path | Notes |
|--------|------|--------|
| **Tenant backend admin dashboard** | `/admin/` | On tenant host, redirects to `/authentication/backend/`. On base domain, main Django Admin. |
| **Default login landing page** | `/authentication/login/` | Same path on base and tenant. |
| **Tenant frontend admin dashboard** | `/authentication/backend/` | Backend dashboard (widgets, students, finance, etc.). |
| **Tenant Parent portal/dashboard** | `/portal/parent/` | Parent dashboard and child links. |
| **Tenant Teacher portal/dashboard** | `/portal/teacher/` | Teacher dashboard (evals/teacher alias). |

On **Option A** (single hostname), the full URL is **base + `/t/<slug>` + path** (e.g. `https://...onrender.com/t/gilead/authentication/login/`).

---

## Main vs tenant admin

| Concept | This project |
|--------|----------------|
| **Main (public) admin** | **Base domain only.** `/admin/` on primary domain. Manage **Schools**, all models. Superuser only. No tenant context. |
| **Tenant admin** | **Backend** at `/authentication/backend/` on the **tenant’s host** (subdomain or custom domain). Data scoped to `request.school`. |
| **Tenant URL** | One per school: **subdomain** (e.g. `gilead-school.school-management-system-2kzk.onrender.com`) or **custom_domain**. Base domain never serves a tenant. |
| **“Domains”** | **School** model: `subdomain`, `custom_domain`, `custom_domain_verified`. No separate Domains table. |

---

## Env (Render and local)

| Variable | Example | Purpose |
|----------|---------|---------|
| **MULTI_TENANT_BASE_DOMAIN** | **Render:** `school-management-system-2kzk.onrender.com` **Local:** `localhost` | Base domain for "no tenant" and subdomain extraction; auto-adds to ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS when set. |
| **RENDER_EXTERNAL_HOSTNAME** | Set by Render automatically | When MULTI_TENANT_BASE_DOMAIN is not set, used as base domain so `/admin/` on the primary URL is always main admin. |
| **CSRF_TRUSTED_ORIGINS** | `https://school-management-system-2kzk.onrender.com` | HTTPS form POSTs (login, etc.). |
| **ALLOWED_HOSTS** | Optional; base + subdomains added when MULTI_TENANT_BASE_DOMAIN is set. | |
| **SINGLE_TENANT** | (optional) | Legacy: force single-school on main URL. |

**Option A (single hostname):** Main URL serves only main admin (`/admin/`, `/super/`). Tenant pages live under **`/t/<school_slug>/`** (e.g. `/t/gilead/authentication/login/`). Root-level tenant paths redirect to `/t/<slug>/...` when exactly one school exists.

---

## Code / config (for Cursor)

- **Main admin:** `config/urls.py` → `path('admin/', admin_site.urls)`; `config/admin.py` → `GileadAdminSite`, superuser-only.
- **Base domain = no tenant:** `apps/schools/middleware.py` → `_is_base_domain()`; on base domain we never set `request.school` (no single-tenant or session fallback).
- **Tenant resolution:** `TenantMiddleware`, `_resolve_school_from_request`: custom_domain → subdomain only; base domain returns None.
- **Redirect to tenant subdomain:** When user logs in on base domain and has a school membership, redirect to `apps.schools.tenant_url.build_tenant_backend_url()`. Same in `redirect_view` and `backend_dashboard`.
- **Tenant Backend:** `apps/accounts/urls.py` → `path("backend/", backend_dashboard)`; on base domain, `backend_dashboard` redirects to tenant subdomain.
- **Platform-level paths (no tenant):** `/admin/`, `/super/`, `/static/`, `/media/`, `/health`, etc. (see `ADMIN_PREFIXES`, `SUPER_PREFIXES` in middleware).

---

## Do not change

- Existing tenant **School** row (name, slug, subdomain, custom_domain).
- Existing **user credentials** (passwords, usernames).
- Tenant-scoped data. Only configure **env** and, if needed, ensure each school’s **subdomain** matches the desired URL.

---

## See also

- [CURRENT_SETUP_AND_GOOD_TO_GO.md](CURRENT_SETUP_AND_GOOD_TO_GO.md) — How things are set up now and good-to-go checklist.
- [MULTI_TENANT_ADMIN_AND_URLS.md](MULTI_TENANT_ADMIN_AND_URLS.md) — Main vs tenant admin, how the codebase does it.
- [RENDER_URL_MAPPING_PLAN.md](RENDER_URL_MAPPING_PLAN.md) — URL map, env, checklist, best practices.
- [ADMIN_AND_TENANT_URLS.md](ADMIN_AND_TENANT_URLS.md) — Discovery and login flows.
- [PLATFORM_ACCESS_AND_CREDENTIALS.md](PLATFORM_ACCESS_AND_CREDENTIALS.md) — Default admin user, credentials, reset.
