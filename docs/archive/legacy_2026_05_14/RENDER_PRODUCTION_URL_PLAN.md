# Render Production URL Mapping & Tenant URL Plan

**Production base URL:** `https://school-management-system-2kzk.onrender.com`

This document maps all entry points to that URL and defines how tenant-specific URLs work **without changing the existing tenant (Gilead) or its credentials**.

---

## 1. Main platform URLs (same for all tenants)

Use the **main domain** for platform-wide access. No tenant context needed.

| Purpose | Full URL |
|--------|----------|
| **Login (main)** | `https://school-management-system-2kzk.onrender.com/authentication/login/` |
| **Django Admin (Configuration Engine)** | `https://school-management-system-2kzk.onrender.com/admin/` |
| **Super Admin (manage all schools)** | `https://school-management-system-2kzk.onrender.com/super/` |
| **Global discovery (email → school)** | `https://school-management-system-2kzk.onrender.com/discover/` |
| **Health** | `https://school-management-system-2kzk.onrender.com/healthz/` |

---

## 2. Current single tenant (Gilead) — no credential changes

You have **one tenant**: Gilead School System Management System (slug `gilead-school`, subdomain `gilead-school`).

- **Do not change:** Any School record (name, slug, subdomain, credentials), or any user/password for that tenant.
- **Current behavior on Render:** The app has only one active school. The middleware already treats the **main host** as that school (single-school fallback in `_resolve_school_from_request`). So:
  - **Main URL = Gilead tenant:**  
    `https://school-management-system-2kzk.onrender.com/`  
    already serves the Gilead tenant (login, backend, portal) because there is only one school.

So today:

| Purpose | Full URL (Gilead) |
|--------|--------------------|
| **Login (Gilead)** | `https://school-management-system-2kzk.onrender.com/authentication/login/` |
| **Backend (Gilead)** | `https://school-management-system-2kzk.onrender.com/authentication/backend/` or `/backend/` |
| **Portal / Preferences** | `https://school-management-system-2kzk.onrender.com/portal/` (and other portal paths) |

No code or DB changes are required for the existing tenant; the main URL is already mapped to it.

---

## 3. Tenant-specific URLs when you add more schools

When you have **multiple** tenants, each should have a stable URL. Two options:

### Option A — Subdomain per tenant (recommended if Render supports it)

- **Base domain on Render:** `school-management-system-2kzk.onrender.com`
- **Tenant URL pattern:** `https://<subdomain>.school-management-system-2kzk.onrender.com/`
- **Example (Gilead):** `https://gilead-school.school-management-system-2kzk.onrender.com/`
- **Example (future school):** `https://another-school.school-management-system-2kzk.onrender.com/`

**Render:** Render allows one hostname per service by default. To use subdomains of that hostname you would need to confirm that `*.school-management-system-2kzk.onrender.com` is accepted (or add the specific subdomains in Render’s custom domains if available). Django’s `ALLOWED_HOSTS` already includes `.onrender.com`, so any `*.onrender.com` host is accepted.

**Env on Render:**
- `MULTI_TENANT_BASE_DOMAIN=school-management-system-2kzk.onrender.com`  
  So discovery and subdomain logic use this base.

**Discovery redirect:** For a user’s school with `subdomain` set, discovery already redirects to `https://<subdomain>.school-management-system-2kzk.onrender.com` when `MULTI_TENANT_BASE_DOMAIN` is set.

### Option B — Path-based tenant URLs (if subdomains are not available)

If Render does **not** serve subdomains for your service, add path-based tenancy so each tenant has a URL like:

- `https://school-management-system-2kzk.onrender.com/t/gilead-school/...`
- `https://school-management-system-2kzk.onrender.com/t/<slug>/authentication/login/`, etc.

This would require:
- A URL prefix (e.g. `/t/<slug>/`) that wraps the main app’s URLs.
- Middleware (or a custom URLconf) that reads `slug` from the path, resolves `School` by slug, sets `request.school` and `session['school_id']`, and strips the prefix before passing to the rest of the app.

No change to the existing Gilead School or its credentials; only routing and middleware additions.

---

## 4. Environment variables on Render

Set these in **Render Dashboard → your Web Service → Environment**:

| Variable | Value | Purpose |
|----------|--------|--------|
| (none required for single tenant) | — | Main URL already maps to Gilead. |
| `MULTI_TENANT_BASE_DOMAIN` | `school-management-system-2kzk.onrender.com` | Use when you want subdomain tenant URLs and discovery redirects to `subdomain.school-management-system-2kzk.onrender.com`. |
| `ALLOWED_HOSTS` | (optional) `school-management-system-2kzk.onrender.com,.school-management-system-2kzk.onrender.com` | Override only if you need to restrict to this app; default already adds `.onrender.com`. |
| `SECURE_SSL_REDIRECT` / `DEBUG` | As you already use | No change. |

Do **not** set anything that would change the existing Gilead School or user credentials (e.g. no migration or script that alters that school or its users).

---

## 5. Checklist: ensure everything is correctly done

- [ ] **Deploy:** Latest code is deployed on Render (so migrations and static are in sync).
- [ ] **Migrations:** In Render Shell (or Release Command):  
  `python manage.py migrate --noinput`
- [ ] **Static:** `python manage.py collectstatic --noinput --clear`
- [ ] **Main URL:** Open `https://school-management-system-2kzk.onrender.com/` → should show login / portal; logging in as admin should work (main URL = Gilead with single-tenant behavior).
- [ ] **Admin:** `https://school-management-system-2kzk.onrender.com/admin/` — login with main platform admin (e.g. admin / your set password).
- [ ] **Super:** `https://school-management-system-2kzk.onrender.com/super/` — only for superuser/SUPERADMIN.
- [ ] **Discover:** `https://school-management-system-2kzk.onrender.com/discover/` — enter email; if one school, redirect to login on main URL (or subdomain if you set `MULTI_TENANT_BASE_DOMAIN` and use subdomains).
- [ ] **Existing tenant:** No changes to Gilead School record (slug, subdomain, name) or to any user/passwords for that tenant.
- [ ] **Future tenants:** When adding schools, set each School’s `subdomain` (and optionally `custom_domain`). If using Option A, set `MULTI_TENANT_BASE_DOMAIN=school-management-system-2kzk.onrender.com` so discovery and subdomain URLs use the Render host.

---

## 6. Summary

| Item | Action |
|------|--------|
| **Base URL** | `https://school-management-system-2kzk.onrender.com` |
| **Single tenant (Gilead)** | Served by main URL; no credential or School changes. |
| **Login / Backend / Portal** | Same base URL + `/authentication/login/`, `/backend/`, `/portal/`, etc. |
| **Multi-tenant later** | Option A: subdomain per tenant (`<subdomain>.school-management-system-2kzk.onrender.com`) with `MULTI_TENANT_BASE_DOMAIN` set; Option B: add path-based `/t/<slug>/` if subdomains are not available. |
| **Render env** | Optional: `MULTI_TENANT_BASE_DOMAIN=school-management-system-2kzk.onrender.com` when using subdomain tenant URLs. |

All tenants are mapped from the main URL; the current one (Gilead) is already correct and unchanged.
