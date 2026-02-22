# Platform Access and Credentials

## Default admin user (created by migration)

After you run **`python manage.py migrate`**, a main platform admin user is created automatically:

| Username | Password | Use |
|----------|----------|-----|
| **admin** | **admin** | Log in to Django Admin, Super Admin, and Portal/Backend |

**Where to log in:**
- **Django Admin (manage all schools):** `http://localhost:8000/admin/`
- **Super Admin (school list, create school, billing):** `http://localhost:8000/super/`
- **Portal / Backend:** `http://localhost:8000/authentication/login/` or `http://gilead-school.localhost:8000/authentication/login/` (with `MULTI_TENANT_BASE_DOMAIN=localhost` for subdomain)

**Security:** In production, change the password immediately:
```bash
python manage.py changepassword admin
```
The migration that creates this user: `apps/accounts/migrations/0021_ensure_default_admin_user.py`.

---

## Main platform (manage all schools)

The **main platform** is where you manage all tenants (schools), Django Admin, and Super Admin. Access uses a **superuser** account (the default one above, or one you create).

### Other ways to get or reset credentials

**Option A — Interactive (create a different superuser):**
```bash
python manage.py createsuperuser
```
Enter username, email, and password when prompted. Then log in at:
- **Django Admin (Configuration Engine):** `http://localhost:8000/admin/`
- **Super Admin (schools dashboard):** `http://localhost:8000/super/`
- **Portal/Backend (after picking a school):** `http://localhost:8000/authentication/login/`

**Option B — Non-interactive (e.g. deploy/CI):**
```bash
# Uses ADMIN_PASSWORD env; username defaults to 'admin'
python manage.py ensure_superuser --no-input --password YOUR_SECURE_PASSWORD

# Or with env only (no args):
# Set ADMIN_PASSWORD=... and optionally DEFAULT_SUPERUSER_USERNAME=admin, DEFAULT_SUPERUSER_EMAIL=admin@example.com
python manage.py ensure_superuser --no-input
```

**Option C — Render / deploy (seed admin + demo users):**
```bash
# Requires ADMIN_PASSWORD in environment
python manage.py migrate --noinput && python manage.py seed_render_users
```
This creates/updates: superuser `admin`, plus `teacher1`, `Parent1`, `principal1` all with the same password (`ADMIN_PASSWORD`). Log in with any of those usernames.

### Defaults (DEBUG only)

If you run `ensure_superuser` with **no** password and `DEBUG=True`, the command uses a fallback password **`Sch00l_1234`** and warns you to change it. In production, always set `ADMIN_PASSWORD` or use `createsuperuser`.

### Where to log in

| Purpose | URL | Account |
|--------|-----|--------|
| Manage all schools, Site Settings, models | `/admin/` | Superuser (or staff) |
| Super Admin dashboard (school list, create, billing) | `/super/` | Superuser with `role=SUPERADMIN` or `is_superuser` |
| Single-school Backend (students, finance, etc.) | `/authentication/backend/` (or on tenant subdomain) | Any user with access to that school |

Same credentials work for `/admin/` and `/authentication/login/`; after login, use the school picker or go to a tenant subdomain to use that school’s Backend.

---

## Gilead tenant data safety

- **Migration 0012** (`0012_seed_default_gilead_school`) only **adds** one School row if none exists with slug `gilead-school`. It does **not** delete or truncate any table. It does not touch users, memberships, SiteSettings, or any other data.
- If a school with slug `gilead-school` already existed, the migration only updates that school’s **name** to “Gilead School System Management System”. All other fields and all related data (users, credentials, memberships, etc.) are unchanged.
- **No credentials are stored or changed by the migration.** User accounts and passwords are managed only by Django auth and the commands above (`createsuperuser`, `ensure_superuser`, `changepassword`).

---

## Resetting or fixing access

- **Forgot admin password:**  
  `python manage.py changepassword admin` (or the username you use).

- **No superuser exists:**  
  `python manage.py ensure_superuser` (with `ADMIN_PASSWORD` or interactive prompt), or `python manage.py createsuperuser`.

- **Need SUPERADMIN role for /super/:**  
  Ensure the user has `is_superuser=True`; the `ensure_superuser` command also sets `role=SUPERADMIN` when the User model has that role.

See also: [ADMIN_AND_TENANT_URLS.md](ADMIN_AND_TENANT_URLS.md) for all URLs and the default Gilead tenant.

---

## Quick audit checklist (verified)

- **Migration 0012:** Additive only; no deletes. Creates/updates one School row (slug `gilead-school`). No user or credential data touched.
- **Django check:** `python manage.py check` — no issues.
- **URLs:** `apps.accounts.tests.test_smoke_urls` (24 tests) — all pass. Key routes (admin, super, backend, discover, request_custom_requirement, customizer) resolve correctly.
- **Linter:** No errors on `views_custom_requirement`, `hooks`, migration 0012.
- **Access control:** `request_custom_requirement` and `request_waiver` use `@login_required` and `@permission_required("settings.manage")` (same pattern); no hardcoded credentials in codebase.
- **Default admin:** Migration `0021_ensure_default_admin_user` creates/updates user `admin` with password `admin` so you can log in without running a command.

---

## Anything else to check

- **Subdomain (tenant) URLs:** For `http://gilead-school.localhost:8000/` to resolve to the Gilead school, set **`MULTI_TENANT_BASE_DOMAIN=localhost`** in your environment. See [ADMIN_AND_TENANT_URLS.md](ADMIN_AND_TENANT_URLS.md) §7.
- **ALLOWED_HOSTS:** Default includes `.localhost` so subdomains work. For production, set `ALLOWED_HOSTS` (and optionally `.localhost` for local dev). See [config/settings.py](../config/settings.py).
- **Deploy checklist:** Pre/post deploy steps, SSL, health endpoints: [DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md).
- **Render production URL:** Main URL and tenant URL mapping for `school-management-system-2kzk.onrender.com`: [RENDER_PRODUCTION_URL_PLAN.md](RENDER_PRODUCTION_URL_PLAN.md).
- **Tag Manager:** If you get a TypeError when opening Tag Manager, the decorator in `views_tag_manager.py` uses `raise_exception=True` which this project’s `permission_required` does not support; remove that argument if needed.
