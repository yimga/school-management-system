# Reaching your tenant (Gilead) and Super-admin

## Why you see "School not found" for Gilead

When you use **runmycampus.com** (or the main domain), the app treats that as the **public** site. Links from Discover/Find send you to **gilead-school.runmycampus.com**. If that subdomain is not set up (no wildcard DNS or no Domain row in the DB), the app cannot resolve the tenant and redirects to **/school-not-found/?slug=gilead-school**.

## Fix: use path-based tenant URLs

You can reach the **same tenant on the main domain** using a path instead of a subdomain.

1. **Set this env var** on Render (or in `.env`):
   ```bash
   USE_PATH_BASED_TENANT_URLS=1
   ```

2. **Use this URL** for Gilead:
   - **Tenant (login/dashboard):**  
     `https://runmycampus.com/t/gilead-school/`  
     Login:  
     `https://runmycampus.com/t/gilead-school/authentication/login/`

3. After redeploy, **Discover** and **Find school** will also link to `https://runmycampus.com/t/gilead-school/` instead of the subdomain.

No changes are made to existing tenant data or credentials; only routing and link generation change when this env is set.

---

## Super-admin (manage all tenants)

Super-admin is the dashboard at **/super/** (tenant list, provisioning, health). It is intended to be used on the **manager** host, e.g. **manager.runmycampus.com/super/**.

### Create admin user (only if it does not exist)

To get a superuser that can access Super-admin **without changing any existing user or tenant**:

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
| Reach Gilead tenant | Set `USE_PATH_BASED_TENANT_URLS=1`, then use `https://runmycampus.com/t/gilead-school/` (and `/t/gilead-school/authentication/login/` to log in). |
| Create Super-admin user (no overwrite) | Run `python manage.py ensure_superadmin` once. Log in with `admin` / `admin`, then change password. |
| Existing tenants/users | No code or DB changes are made to existing tenant data or credentials. |
