# Admin and Tenant URLs Reference

This project uses **single-database multi-tenancy**: one Django app, one admin, with tenants (schools) identified by **subdomain** or **custom domain**. The middleware sets `request.school`; there are no separate PostgreSQL schemas per tenant.

---

## 1. Main (Platform) Admin — Configuration Engine

**URL:** `/admin/`

- **Local:** `http://localhost:8000/admin/` or `http://127.0.0.1:8000/admin/`
- **Production:** `https://yourdomain.com/admin/`

**What you see:** Django Admin (Unfold). After logging in with a **superuser** account you manage all shared and tenant-scoped models (Schools, SiteSettings, CustomFeatureTicket, FeatureFragment, People, Finance, etc.). Data is filtered by `School` (FK) where applicable.

**Prerequisite:** Create a superuser (or use `ensure_superuser` / `seed_render_users`). See [PLATFORM_ACCESS_AND_CREDENTIALS.md](PLATFORM_ACCESS_AND_CREDENTIALS.md) for full details.

```bash
python manage.py createsuperuser
```

**Config:** [config/urls.py](../config/urls.py) — `path('admin/', admin_site.urls)`  
**Custom admin site:** [config/admin.py](../config/admin.py) — `admin_site` (not `django.contrib.admin.site`).

---

## 2. Super Admin — Platform Owner Dashboard

**URL:** `/super/`

- **Local:** `http://localhost:8000/super/`
- **Production:** `https://yourdomain.com/super/`

**What you see:** Multi-tenant control center: list of all schools, create school wizard, financial bento, health block, sync repair, etc.

**Prerequisite:** User must have `role == 'SUPERADMIN'` or `is_superuser`. Middleware: `TenantSuperAdminRequiredMiddleware` restricts `/super/` to that role.

**URLs under `/super/`:**
- `/super/` — dashboard (`super:dashboard`)
- `/super/create/` — create school wizard
- `/super/sync-repair/<school_id>/` — sync repair for a school
- `/super/parent-tenant/` — parent tenant dashboard

**Config:** [config/urls.py](../config/urls.py) — `path('super/', include(('apps.schools.super_urls', 'super'), namespace='super'))`

---

## 3. Tenant (School) Backend — Per-School Admin Center

Each school is reached by **subdomain** (or custom domain). The same paths exist on every host; the **host** determines which school’s data you see.

**URL pattern (subdomain):**

- **Local:** `http://<subdomain>.localhost:8000/` (e.g. `http://greenwood.localhost:8000/`)
- **Production:** `https://<subdomain>.<yourdomain>.com/` (e.g. `https://greenwood.yoursystem.com/`)

**Base domain:** Set in env as `MULTI_TENANT_BASE_DOMAIN` (e.g. `yoursystem.com`). If unset, subdomain is derived from the host (e.g. first label of `greenwood.localhost` → `greenwood`).

**Main tenant “admin” (Backend Console):**

- **Path:** `/authentication/backend/` (or short redirect: `/backend/` → redirects here)
- **Full tenant URL examples:**
  - `http://greenwood.localhost:8000/backend/` → redirects to Backend Console for school with subdomain `greenwood`
  - `http://greenwood.localhost:8000/authentication/backend/` — same, canonical path

**What you see:** Backend dashboard (widgets, students, finance, reports, Site Settings/Customizer, Request custom requirement, etc.). All data is scoped to the school resolved from the host (or session).

**Prerequisite:** User must belong to that tenant (school) and have appropriate permissions (`is_staff`, or role such as ADMIN/IT_ADMIN/LEADERSHIP, plus feature permissions like `settings.manage`). Users are linked to schools via your auth/tenant model; there is no separate “tenant schema” — the same database and same `/admin/` are used, with middleware and `request.school` providing tenant context.

**Config:**  
- Tenant resolution: [apps/schools/middleware.py](../apps/schools/middleware.py) — `TenantMiddleware` (subdomain + custom domain + `SINGLE_TENANT`)  
- Backend URL: [apps/accounts/urls.py](../apps/accounts/urls.py) — `path("backend/", backend_dashboard, name="backend_dashboard")`  
- Root redirect: [config/urls.py](../config/urls.py) — `path('backend/', ... redirect to accounts:backend_dashboard)`

---

## 4. Global Login / Discovery (Section 8)

**URL:** `/discover/`

- **Local:** `http://localhost:8000/discover/`
- **Production:** `https://yourdomain.com/discover/`

**What you see:** Public “global login” page: user enters email, system finds the school and redirects to that school’s login (subdomain or custom domain).

**Config:** [config/urls.py](../config/urls.py) — `path('discover/', global_login_discovery, name='global_login_discovery')`

---

## 5. Quick Reference Table

| Purpose              | URL (relative)        | Example (local)                          | Access                    |
|----------------------|-----------------------|------------------------------------------|---------------------------|
| Platform admin       | `/admin/`             | `http://localhost:8000/admin/`           | Superuser / staff         |
| Super Admin dashboard| `/super/`             | `http://localhost:8000/super/`           | SUPERADMIN / superuser    |
| Tenant backend       | `/backend/` or `/authentication/backend/` | `http://greenwood.localhost:8000/backend/` | School users (staff/roles) |
| Global login         | `/discover/`          | `http://localhost:8000/discover/`        | Public                    |

---

## 6. For Cursor / Config Checklist

- **Single Django admin:** One `admin_site` at `/admin/`; no `SHARED_APPS` / `TENANT_APPS` (this is not django-tenants). All apps use the same database; tenant is determined by middleware and `School` FK.
- **Tenant resolution:** `MULTI_TENANT_BASE_DOMAIN` (env) for subdomain parsing; `School.subdomain` and `School.custom_domain` (+ `custom_domain_verified`) in [apps/schools/models.py](../apps/schools/models.py).
- **Domains / schools:** In the main admin (`/admin/`), use the **Schools** (and related) models to see and edit which subdomains/custom domains exist. There is no separate “Domains” table; each `School` has `subdomain` and `custom_domain` fields.
- **ALLOWED_HOSTS:** [config/settings.py](../config/settings.py) — from env `ALLOWED_HOSTS` (default `localhost,127.0.0.1,.local`). For subdomains locally use e.g. `.localhost`; for production include your base domain and any custom domains.

---

## 7. Default tenant (Gilead School System Management System)

After migrations, **one default tenant** is created so the system is usable immediately:

| Field      | Value                                |
|-----------|--------------------------------------|
| **Name**  | Gilead School System Management System |
| **Slug**   | `gilead-school`                      |
| **Subdomain** | `gilead-school`                  |

**Tenant URLs for this school (local):**

- **Backend:** `http://gilead-school.localhost:8000/backend/` or `http://gilead-school.localhost:8000/authentication/backend/`
- **Login:** `http://gilead-school.localhost:8000/authentication/login/`
- **Discover:** `http://localhost:8000/discover/` (then enter a user email to get redirected to this school's login)

**Local subdomain:** For `gilead-school.localhost` to resolve to this tenant, set `MULTI_TENANT_BASE_DOMAIN=localhost` in your env (or leave unset and use a host with 3+ parts). `ALLOWED_HOSTS` defaults include `.localhost` so subdomains of localhost are accepted.

**Seed:** Migration [apps/schools/migrations/0012_seed_default_gilead_school.py](../apps/schools/migrations/0012_seed_default_gilead_school.py) runs `get_or_create` for this school. If you already have a school with slug `gilead-school`, its name is updated to the full name above.

---

## 8. URL verification (resolved paths)

These are the canonical resolved paths (accounts app is mounted at `/authentication/`):

| Name | Resolved path |
|------|----------------|
| Platform admin | `/admin/` |
| Super dashboard | `/super/` |
| Backend dashboard | `/authentication/backend/` |
| Backend (short) | `/backend/` redirects to `/authentication/backend/` |
| Login | `/authentication/login/` |
| Global discovery | `/discover/` |
| Request custom requirement | `/siteconfig/request-custom-requirement/` |
| Site config / Customizer | `/studio/` (legacy `/siteconfig/customizer/` redirects here) |

To confirm in your project: `python manage.py shell` then `from django.urls import reverse; print(reverse('accounts:backend_dashboard'))` should output `/authentication/backend/`.
