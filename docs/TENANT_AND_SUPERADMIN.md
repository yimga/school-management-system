# Reaching your tenant (Gilead) and Super-admin

## Tenant URL configuration (subdomain only)

**All tenants use subdomain (and verified custom domain) only.** There is no path-based tenant mode.

- **Canonical tenant URL:** `https://<subdomain>.<base_domain>` (e.g. `https://gilead-school.runmycampus.com`).
- **Custom domain:** If a school has a verified custom domain, that host is used instead of the subdomain.
- **Requests to `/t/<slug>/` on the base domain** are permanently redirected to the tenant subdomain (or custom domain). The app never serves tenant content on the base domain path.

Do **not** set `USE_PATH_BASED_TENANT_URLS`; it is no longer used. Portal links (Discover, Find school, school-not-found) always point to the subdomain URL.

## Why you see "School not found" for Gilead

When you use **runmycampus.com** (or the main domain), the app treats that as the **public** site. Links from Discover/Find send you to **gilead-school.runmycampus.com**. If that subdomain is not set up (no wildcard DNS or no Domain row in the DB), the app cannot resolve the tenant and redirects to **/school-not-found/?slug=gilead-school**.

**Fix:** Ensure the tenant subdomain is reachable: wildcard DNS for `*.runmycampus.com` (or your base domain) and a `Domain` (or `SchoolDomain`) row for the school’s subdomain so the app can resolve the tenant by host.

---

## Super-admin (manage all tenants)

Super-admin is the dashboard at **/super/** (tenant list, provisioning, health). It is intended to be used on the **manager** host, e.g. **manager.runmycampus.com/super/**.

### Create or ensure admin user

On Render, **seed_render_users** (run on every predeploy) ensures the platform super-admin **admin** / **admin**. It does not use `ADMIN_PASSWORD` for the admin account; that env var is used only for tenant demo users (teacher1, Parent1, principal1).

To create the super-admin **only if** no user with username **admin** exists (no overwrite):

```bash
python manage.py ensure_superadmin
```

This creates a user **only if** no user with username **admin** exists:

- **Username:** `admin`
- **Password:** `admin`

If a user **admin** already exists, the command does nothing (no password or data change).

### Logging in as Super-admin

1. Go to **manager.runmycampus.com/authentication/login/** (or your manager host).
2. Log in with `admin` / `admin`.
3. Open **manager.runmycampus.com/super/**.

If you only have one host (e.g. runmycampus.com), check **ACCESS_POINTS.md**: base domain may redirect **/super/** to the manager host. If you have no separate manager host, ensure **/super/** is reachable on your main URL (see `ReservedPublicHostAccessMiddleware` and `UrlConfSwitcherMiddleware`).

### Change password after first login

For security, change the default password:

```bash
python manage.py changepassword admin
```

---

## Summary

| Goal | What to do |
|------|------------|
| Reach Gilead tenant | Use subdomain: `https://gilead-school.runmycampus.com` (and `/authentication/login/` there). Ensure wildcard DNS and Domain/SchoolDomain for the subdomain. |
| Create Super-admin user (no overwrite) | Run `python manage.py ensure_superadmin` once. Log in with `admin` / `admin`, then change password. |
| Existing tenants/users | No code or DB changes are made to existing tenant data or credentials. |
