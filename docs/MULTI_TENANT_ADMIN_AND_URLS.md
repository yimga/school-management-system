# Multi-Tenant Admin and Tenant-Specific URLs

**Quick reference:** [QUICK_REFERENCE_MULTI_TENANT.md](QUICK_REFERENCE_MULTI_TENANT.md) — one-page URLs and env summary.

This project **does not use django-tenants** (no PostgreSQL schemas per tenant). It uses **one database**, **one Django admin**, and **tenant resolution by host** (subdomain or custom domain). The concepts of "Main (Public) Admin" and "Individual Tenant Admin" map as below. **Existing tenant credentials and data are never changed by URL or env configuration.**

---

## 1. Main (Public) Admin — Platform / Configuration Engine

**What it is:** The single Django Admin where you, as platform owner, manage all tenants (schools) and shared config.

| Item | This project | django-tenants (reference) |
|------|---------------------------|----------------------------|
| **URL** | `/admin/` on the **primary domain** | Same idea: main domain at `/admin/` |
| **Example (Render)** | `https://school-management-system-2kzk.onrender.com/admin/` | — |
| **Example (local)** | `http://localhost:8000/admin/` | — |
| **What you see** | Schools, SiteSettings, Users, People, Finance, etc. (all models). Data is in one DB; tenant-scoped models use a `School` FK. | Public schema; Tenant/Domain models |
| **Prerequisite** | A **superuser** (e.g. created with `python manage.py createsuperuser` or migration `0021` default admin). | Superuser in public schema |
| **Access control** | [config/admin.py](../config/admin.py): `GileadAdminSite.has_permission` requires `is_staff` and `is_superuser`. | — |
| **SHARED_APPS / TENANT_APPS** | **Not used.** We have one Django app list; no schema switching. | Used to split apps between public and tenant schemas |

**Best practice:** Use one superuser for the main admin. Log in at the **primary domain** (e.g. `https://school-management-system-2kzk.onrender.com/admin/`). Do not change existing tenant users or passwords when configuring this.

---

## 2. Individual Tenant Admin — Per-School Backend

**What it is:** Each school’s operational dashboard (Backend), not a second Django Admin. The **host** (subdomain or custom domain) identifies the tenant; the same paths are used on every host.

| Item | This project | django-tenants (reference) |
|------|---------------------------|----------------------------|
| **URL pattern** | **Tenant-specific host** + `/authentication/backend/` (or `/backend/` redirect). | Tenant subdomain + `/admin/` |
| **Example (subdomain)** | `https://gilead-school.school-management-system-2kzk.onrender.com/authentication/backend/` | `http://greenwood.yoursystem.com/admin/` |
| **Example (custom domain)** | `https://portal.gileadschool.com/authentication/backend/` | — |
| **What you see** | Backend dashboard (widgets, students, finance, reports, Customizer, Request custom requirement). All data is scoped to `request.school` (set by middleware). | Tenant schema data |
| **Prerequisite** | User must be linked to that school (e.g. membership) and have appropriate role/permissions (`is_staff`, ADMIN, etc.). **Same User table** for all tenants; no per-tenant schema. | User in that tenant’s schema with is_staff |
| **How tenant is chosen** | Middleware: host → subdomain or custom_domain → School row → `request.school`. If exactly one school (or `SINGLE_TENANT=true`), main domain can also resolve to that school. | Host → Domain → Tenant schema |

**Best practice:** Give each tenant a **custom URL** so you can differentiate schools:

- **By subdomain:** Set each school’s **subdomain** (e.g. `gilead-school`, `greenwood`). Tenant URL = `https://<subdomain>.<MULTI_TENANT_BASE_DOMAIN>/`.
- **By custom domain:** Set each school’s **custom_domain** (e.g. `portal.gileadschool.com`) and **custom_domain_verified** = True. Tenant URL = `https://<custom_domain>/`.

**We do not change** the existing tenant’s name, slug, subdomain, or any user credentials. Only configure env (e.g. `MULTI_TENANT_BASE_DOMAIN`) and, if you want subdomain URLs, ensure the existing school’s **subdomain** matches the URL you want (e.g. `gilead-school` → `https://gilead-school..../`).

---

## 3. How the codebase handles it

- **Main admin:** [config/urls.py](../config/urls.py) mounts `admin_site.urls` at `path('admin/', ...)`. [config/admin.py](../config/admin.py) restricts access to superusers. No schema switch; one DB.
- **Tenant resolution:** [apps/schools/middleware.py](../apps/schools/middleware.py) `TenantMiddleware` and `_resolve_school_from_request()`:
  1. **Custom domain:** match `request.get_host()` to `School.custom_domain` (verified).
  2. **Subdomain:** extract subdomain from host using `MULTI_TENANT_BASE_DOMAIN`; match to `School.subdomain` or `School.slug`.
  3. **Single-tenant fallback:** if `SINGLE_TENANT=true` or exactly one active school, use that school on the main domain.
  4. **Session fallback:** if no host match, use `request.session['school_id']` if set (e.g. after school picker).
- **Tenant “admin” (Backend):** [apps/accounts/urls.py](../apps/accounts/urls.py) `path("backend/", backend_dashboard, ...)`. Views use `request.school` (set by middleware) to scope data. No separate `/admin/` per tenant.
- **Domain list:** We do **not** have a separate “Domains” table. The **School** model has `subdomain` and `custom_domain` (and `custom_domain_verified`). In the main admin (`/admin/`), use **Schools** to see and edit which subdomain/custom domain each school uses.

---

## 4. Tenant-specific URL per tenant name (differentiate schools)

To have **one distinct URL per tenant**:

1. **Subdomain = tenant identifier**  
   Set each school’s **subdomain** to a unique value (e.g. same as slug or a short name):
   - Gilead: `subdomain` = `gilead-school` → `https://gilead-school.school-management-system-2kzk.onrender.com/`
   - Another: `subdomain` = `greenwood` → `https://greenwood.school-management-system-2kzk.onrender.com/`

2. **Set MULTI_TENANT_BASE_DOMAIN**  
   On Render: `MULTI_TENANT_BASE_DOMAIN=school-management-system-2kzk.onrender.com` so subdomain extraction works.

3. **Optional: custom domain per school**  
   For a school, set **custom_domain** (e.g. `portal.gileadschool.com`) and **custom_domain_verified** = True. That school is then reached at `https://portal.gileadschool.com/` (CNAME to your Render service).

4. **Do not change existing tenant**  
   For the current single tenant (Gilead), do not rename the school, change slug/subdomain, or change any user credentials. If it already has `subdomain=gilead-school`, keep it; only ensure env and DNS (if using custom domain) are correct.

---

## 5. Quick reference (this project vs django-tenants)

| Concept | This project | django-tenants |
|--------|----------------|-----------------|
| Main (public) admin | `/admin/` on primary domain; superuser | `/admin/` on main domain; public schema |
| Tenant admin | **Backend** at `/authentication/backend/` on **tenant host** | `/admin/` on tenant subdomain (tenant schema) |
| Tenant URL | Subdomain or custom_domain → one URL per school | Subdomain (or domain) per tenant |
| Database | One DB; School FK and RLS for tenant data | One DB; one schema per tenant |
| “Domains” table | School.subdomain + School.custom_domain | Domain model in public schema |
| SHARED_APPS / TENANT_APPS | Not used | Used |

---

## 6. Original tenant credentials and data

- **No code or migration** in this plan changes the existing tenant’s:
  - School name, slug, subdomain, custom_domain, or any other School fields
  - User accounts or passwords
  - Any tenant-scoped data (students, finance, etc.)
- **Only** the following are configured: environment variables (e.g. `MULTI_TENANT_BASE_DOMAIN`, `CSRF_TRUSTED_ORIGINS`) and, if you want subdomain URLs, ensuring the existing school’s **subdomain** matches the desired URL (already set to `gilead-school` by migration 0012; no change required if you keep it).

See also: [QUICK_REFERENCE_MULTI_TENANT.md](QUICK_REFERENCE_MULTI_TENANT.md), [ADMIN_AND_TENANT_URLS.md](ADMIN_AND_TENANT_URLS.md), [PLATFORM_ACCESS_AND_CREDENTIALS.md](PLATFORM_ACCESS_AND_CREDENTIALS.md), [RENDER_URL_MAPPING_PLAN.md](RENDER_URL_MAPPING_PLAN.md).
