# Render URL mapping plan

**Quick reference:** [QUICK_REFERENCE_MULTI_TENANT.md](QUICK_REFERENCE_MULTI_TENANT.md) — one-page URLs and env.

**Main deployed URL:** `https://school-management-system-2kzk.onrender.com/`

**Goal:** Map everything so the main URL and (when you have more than one) tenant-specific URLs work. Each tenant has a **custom URL** (subdomain or custom domain) to differentiate schools. Do not change the existing single tenant credentials or data. (This app does not use django-tenants; see [MULTI_TENANT_ADMIN_AND_URLS.md](MULTI_TENANT_ADMIN_AND_URLS.md).)

---

## 1. How tenant resolution works today

- **Subdomain:** `https://<subdomain>.<base>/` → school with that `subdomain` or `slug` (e.g. `gilead-school.school-management-system-2kzk.onrender.com`).
- **Custom domain:** `https://school.example.com/` → school with `custom_domain` = that host (verified).
- **Single-tenant fallback:** If there is **exactly one active school** in the DB (or `SINGLE_TENANT=true`), the app uses that school on the **main URL** with no subdomain.

So with **one tenant (Gilead)** and the main URL only:

- `https://school-management-system-2kzk.onrender.com/` already resolves to that single school. No credential or tenant data changes needed.

---

## 2. URL map on Render (single tenant)

| Purpose | URL | Who |
|--------|-----|-----|
| **Main site / login** | `https://school-management-system-2kzk.onrender.com/` | Redirects to login or dashboard |
| **Login** | `https://school-management-system-2kzk.onrender.com/authentication/login/` | Staff, admin, teachers, parents |
| **Backend (tenant)** | `https://school-management-system-2kzk.onrender.com/authentication/backend/` | Same host → same (only) tenant |
| **Django Admin** | `https://school-management-system-2kzk.onrender.com/admin/` | Superuser |
| **Super Admin** | `https://school-management-system-2kzk.onrender.com/super/` | Superuser (SUPERADMIN) |
| **Discover** | `https://school-management-system-2kzk.onrender.com/discover/` | Public; redirects to tenant login |
| **Request custom requirement** | `https://school-management-system-2kzk.onrender.com/siteconfig/request-custom-requirement/` | Users with `settings.manage` |

All of these use the **same** host. With one school, the middleware treats that host as the Gilead tenant (single-tenant fallback). No change to the existing tenant or its credentials.

---

## 3. Environment variables on Render

Set these in **Render Dashboard → your Web Service → Environment**:

| Variable | Value | Why |
|----------|--------|-----|
| **ALLOWED_HOSTS** | `school-management-system-2kzk.onrender.com` | Allow the Render host (optional if you already append `.onrender.com` in code; then this can override for a single host). |
| **MULTI_TENANT_BASE_DOMAIN** | `school-management-system-2kzk.onrender.com` | So subdomain extraction works when you add tenant subdomains later (e.g. `gilead-school.school-management-system-2kzk.onrender.com`). |
| **CSRF_TRUSTED_ORIGINS** | `https://school-management-system-2kzk.onrender.com` | So HTTPS form POSTs (login, etc.) work. |
| **SECRET_KEY** | (your production secret) | Required. |
| **DATABASE_URL** | (Render PostgreSQL or your DB URL) | Required. |

Optional for single-tenant behavior:

- **SINGLE_TENANT** = `true` → always use the one active school on the main URL (explicit; otherwise the “exactly one school” logic does the same).

Do **not** change any user or school credentials in the DB; only configure env.

---

## 4. When you add more tenants (later)

Each tenant can have a “custom URL” in one of these ways:

**Option A – Subdomains (if Render supports them)**  
If Render allows wildcard or multiple hostnames for the same service:

- Tenant 1: `https://gilead-school.school-management-system-2kzk.onrender.com/`
- Tenant 2: `https://another-school.school-management-system-2kzk.onrender.com/`

Then:

- Keep **MULTI_TENANT_BASE_DOMAIN** = `school-management-system-2kzk.onrender.com`.
- Each school’s **subdomain** (e.g. `gilead-school`) must match the first part of the host. No credential changes for existing tenant.

**Option B – Custom domains (recommended for production)**  
Each school gets its own domain pointing to the same Render service:

- Gilead: `https://portal.gileadschool.com` → CNAME to `school-management-system-2kzk.onrender.com` (or Render’s target).
- In Django Admin, set that school’s **custom_domain** = `portal.gileadschool.com` and mark **custom_domain_verified** = True (after DNS/SSL is ok).

Again, no change to existing tenant credentials; only add new schools and (optionally) custom domains.

**Option C – Path-based (e.g. /t/gilead-school/)**  
Not implemented today. Would require new middleware/URLs to choose school from path; keep current behavior and use A or B for “custom URLs” per tenant.

---

## 5. Checklist (everything properly set)

For a one-page summary of URLs and env, see [QUICK_REFERENCE_MULTI_TENANT.md](QUICK_REFERENCE_MULTI_TENANT.md).

- [ ] **Render env**
  - [ ] `MULTI_TENANT_BASE_DOMAIN` = `school-management-system-2kzk.onrender.com`
  - [ ] `CSRF_TRUSTED_ORIGINS` includes `https://school-management-system-2kzk.onrender.com`
  - [ ] `ALLOWED_HOSTS` includes the host (or keep default that adds `.onrender.com`)
  - [ ] `SECRET_KEY` and `DATABASE_URL` set
- [ ] **Deploy**
  - [ ] Code deployed (migrations and static files run via Release Command or Shell: `migrate --noinput`, `collectstatic --noinput --clear`)
- [ ] **No credential changes**
  - [ ] Do not modify the existing tenant School row credentials or linked users; only env and URL mapping.
- [ ] **Verify**
  - [ ] Open `https://school-management-system-2kzk.onrender.com/` → login or home.
  - [ ] Log in with existing tenant credentials → Backend/dashboard for that tenant.
  - [ ] Log in with main admin (admin / admin if you use the default) at `/admin/` and `/super/`.
  - [ ] `/discover/` loads and (after entering an email) redirects to login.

---

## 6. Best practices (summary)

- **Main (public) admin:** Use the **primary domain** for `/admin/` and `/super/` with a superuser. No tenant context required.
- **Tenant admin (Backend):** Use the **tenant custom URL** (subdomain or custom domain) so the host identifies the school; same path `/authentication/backend/` everywhere.
- **One URL per tenant name:** Set each school **subdomain** (e.g. `gilead-school`) so URL is `https://<subdomain>.school-management-system-2kzk.onrender.com/`. Or use **custom_domain** per school.
- **Existing tenant:** Do not change the current tenant School row or any user credentials; only set env vars. The Gilead school already has `subdomain=gilead-school` (migration 0012).
- **Domains list:** In main admin, use **Schools** to see/edit **subdomain** and **custom_domain** (no separate Domains table).

---

## 7. One-line summary

**Single tenant:** Main URL is the tenant URL (single-school fallback). Set **MULTI_TENANT_BASE_DOMAIN** and **CSRF_TRUSTED_ORIGINS** on Render; do not change existing tenant credentials. For more tenants, give each a custom URL via subdomain or custom domain. See [MULTI_TENANT_ADMIN_AND_URLS.md](MULTI_TENANT_ADMIN_AND_URLS.md).
