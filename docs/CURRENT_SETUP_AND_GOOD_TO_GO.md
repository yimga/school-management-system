# Current Setup & Good-to-Go Checklist

Short summary of how multi-tenant admin and the **default demo school** (historical slug `gilead-school` from shipped migrations) are set up, and what to verify before go-live.

**Product naming:** The platform is **RunMyCampus**. The slug and legacy seed strings below are **database history**, not the product name. See [GILEAD_REFERENCE_CLASSIFICATION.md](GILEAD_REFERENCE_CLASSIFICATION.md).

**Quick reference:** [QUICK_REFERENCE_MULTI_TENANT.md](QUICK_REFERENCE_MULTI_TENANT.md)

---

## How things are set up

### 1. Default demo school (historical migrations)

- **Migration 0012** (`apps/schools/migrations/0012_seed_default_gilead_school.py`): Ensures one school exists with `slug=gilead-school`, `name="Gilead School System Management System"`, `subdomain=gilead-school`, `is_active=True`. Additive only; does not delete or overwrite existing data.
- **Migration 0013** (`apps/schools/migrations/0013_link_default_admin_to_gilead.py`): Links the default platform admin user to that school via **SchoolMembership** so that user can use the tenant Backend and the school picker shows the default row. No password or tenant data change.

### 2. Main (public) admin

- **URL:** `/admin/` on the **primary domain** (e.g. `https://school-management-system-2kzk.onrender.com/admin/` or `http://localhost:8000/admin/`).
- **Access:** Superuser only (`config/admin.py` → `PlatformAdminSite` / `BaseRunMyCampusAdminSite` permission rules).
- **Behavior:** Middleware treats `/admin/` as platform-level: `request.school = None` so the admin is not tied to a tenant.
- **Default superuser:** Migration 0021 creates `admin` / `admin` (change password in production).

### 3. Tenant admin (Backend)

- **URL:** `/authentication/backend/` (or `/backend/`) on the **tenant host** (main domain when single-tenant, or subdomain/custom domain when multi-tenant).
- **Access:** Users with permission and, for non-superusers, a **SchoolMembership** for that school. Superusers can access any tenant; login sets `school_id` from single-tenant or membership.
- **Behavior:** Middleware resolves tenant from host (custom_domain → subdomain → single-tenant/session), sets `request.school` and `request.session['school_id']`.

### 4. Env and hosts

- **MULTI_TENANT_BASE_DOMAIN:** When set (e.g. on Render), the app adds that host and its subdomains to **ALLOWED_HOSTS** and adds `https://<base>` to **CSRF_TRUSTED_ORIGINS** (`config/settings.py`).
- **Local:** Default `ALLOWED_HOSTS` includes `localhost`, `127.0.0.1`, `.local`, `.localhost` so you can test subdomains (e.g. `gilead-school.localhost:8000`).

---

## Good-to-go checklist

Use this to confirm the default demo tenant and access are ready.

- [ ] **Migrations applied**  
  `python manage.py migrate` — includes 0012 (default demo school seed), 0021 (admin user), 0013 (admin → demo school membership).

- [ ] **Main admin**  
  Open `/admin/` on the primary domain → log in with `admin` / `admin` (or your superuser). You should see Schools and other models. No tenant context.

- [ ] **Tenant Backend**  
  Open `/` or `/authentication/login/` on the same host → log in with `admin` (or a user with membership to the default demo school). After login you should land on the Backend dashboard for that school (single-tenant on main URL).

- [ ] **Default demo school row**  
  In main admin, open **Schools**. The seeded row should still have `slug=gilead-school`, `subdomain=gilead-school` unless you intentionally renamed it. Do not change slug, subdomain, or user credentials unless you intend to.

- [ ] **Render (when deployed)**  
  Set **MULTI_TENANT_BASE_DOMAIN** = `school-management-system-2kzk.onrender.com` (and **CSRF_TRUSTED_ORIGINS** if you need more origins). Run `migrate` and `collectstatic` after deploy. See [RENDER_URL_MAPPING_PLAN.md](RENDER_URL_MAPPING_PLAN.md).

- [ ] **Production security**  
  Change the default admin password: `python manage.py changepassword admin`.

---

## Optional improvements (already done or not required)

| Item | Status |
|------|--------|
| Main admin platform-level (no tenant) | Done: `/admin/` in `ADMIN_PREFIXES` in middleware. |
| ALLOWED_HOSTS/CSRF from MULTI_TENANT_BASE_DOMAIN | Done: in `config/settings.py`. |
| Default admin linked to demo school | Done: migration 0013. |
| Path-based tenancy (e.g. `/t/slug/`) | Not implemented; use subdomain or custom domain. |
| Separate “Domains” table | Not used; use School `subdomain` and `custom_domain`. |

---

## See also

- [QUICK_REFERENCE_MULTI_TENANT.md](QUICK_REFERENCE_MULTI_TENANT.md) — One-page URLs and env.
- [MULTI_TENANT_ADMIN_AND_URLS.md](MULTI_TENANT_ADMIN_AND_URLS.md) — Main vs tenant admin, codebase behavior.
- [RENDER_URL_MAPPING_PLAN.md](RENDER_URL_MAPPING_PLAN.md) — Render URL map, env, checklist.
- [PLATFORM_ACCESS_AND_CREDENTIALS.md](PLATFORM_ACCESS_AND_CREDENTIALS.md) — Default admin, credentials, reset.
