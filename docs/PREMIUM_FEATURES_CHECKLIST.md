# Premium features & feel — checklist

Use this to confirm all premium/high-end styling and features are in place before testing and push.

---

## Control plane & manager (superadmin)

| Item | Location | Status |
|------|----------|--------|
| Control plane skeleton | `templates/control_plane_skeleton.html` | Navy/gold `:root`, `control-plane-shell`, `cp-surface`, design-tokens, manager-control-plane.css, platform-high-end.css, surface-themes |
| Manager login | `templates/auth/manager_login.html` | Extends control_plane_skeleton, manager-login.css, `#cp-main-content` |
| Admin (Configuration Engine) login | `templates/auth/admin_login.html` | Extends control_plane_skeleton, manager-login.css, form/CSRF/next, password reset link, Back to public site |
| Admin shell (all /admin/ pages) | `templates/admin/base_site.html` | manager-control-plane.css, platform-high-end.css, admin-manager-shell.css; body classes `control-plane-shell`, `admin-manager-shell`, `cp-surface` |
| Superadmin dashboard at /admin/ | `templates/admin/index_superadmin.html` | Heavier structure: hero (Control plane, Command center, Billing), platform stats, app grid; navy/gold |
| Control plane pages (/super/, marketplace) | control_plane_base.html, super_*.html, marketplace/*.html | Extend skeleton or base; manager-control-plane.css, control-plane-shell class |

---

## Tenant

| Item | Location | Status |
|------|----------|--------|
| Tenant admin index at /admin/ | `templates/admin/index_tenant.html` | Backend-first: large Backend Dashboard tile, hero, quick-config grid; school theme (SITE_ADMIN_THEME) in `.tenant-admin-index` |
| Backend base & dashboard | `templates/backend_base.html`, `templates/accounts/backend_dashboard.html` | portal-premium-shell.css, backend-shell-parity, backend themes |
| Portal base | `templates/portal_base.html` | platform-high-end.css, portal-premium-shell.css |

---

## Login & alerts

| Item | Location | Status |
|------|----------|--------|
| Login alerts (errors, warnings) | `static/css/manager-login.css` | `.admin-login-alert`, `.manager-login-alert`, `.alert-danger`, `.alert-warning` visible on dark card |
| Password reset link | `static/css/manager-login.css` | `.admin-login-reset a` visible, gold on hover |
| Skip to main content | control_plane_skeleton, admin/base_site | `#cp-main-content` on main section; skip link in skeleton |

---

## Static assets (all must exist)

- `static/css/manager-control-plane.css`
- `static/css/manager-login.css`
- `static/css/admin-manager-shell.css`
- `static/css/platform-high-end.css`
- `static/css/portal-premium-shell.css`
- `static/css/surface-themes.css`
- `static/css/design-tokens.css`
- `static/css/design-system-unified.css`

---

## Routing

- **Admin index:** `config/admin.py` → `index()` uses `index_superadmin.html` when `public_host_kind == "manager"`, else `index_tenant.html`.
- **Logins:** Admin login template from `config/admin.py` `login_template`; manager login from accounts view when `public_host_kind == "manager"`.

---

## Quick test before push

1. `python manage.py check` — no issues.
2. Manager host: open /admin/ login → control-plane shell, navy/gold; after login → superadmin dashboard (hero + Control plane / Command center / Billing).
3. Tenant host: login to backend → open /admin/ → tenant dashboard (Backend Dashboard tile first, school theme).
4. Logout from admin → login page uses same control-plane shell.
5. Tenant backend dashboard: premium shell (portal-premium-shell), school theme, no regression.

Then: run your usual test suite, commit, push.
