# White-labeling: Logo & primary color injection (Phase 16)

## Single source of truth

- **SiteSettings** (and active ThemePack where used): `logo`, `favicon`, `primary_color`, `accent_color`, and theme overrides.
- **Context:** `apps/siteconfig/context_processors.py` exposes `SITE_LOGO_URL`, `SITE_FAVICON_URL`, `SITE_ADMIN_LOGO_URL`, `ADMIN_RESOLVED_PRIMARY`, etc.

## Injection points

| Surface | Logo | Primary / accent |
|--------|------|-------------------|
| **Login** | `templates/auth/login.html` — hero uses `SITE_LOGO_URL`; `base.html` sets `--school-primary` / `--school-accent` from SITE. | Hero gradient and buttons use SITE colors; CSS vars available. |
| **Portal** | Header/footer use `SITE_LOGO_URL` and `--header-brand-bg` (from theme in portal_base). | `portal_base.html` sets `:root { --school-primary, --school-accent }` from theme. |
| **Backend** | Same as portal or backend-specific logo from admin theme. | `backend_base.html` overrides theme from `SITE_ADMIN_THEME`. |
| **Admin (Django)** | Admin sidebar/header use `SITE_ADMIN_LOGO_URL` and theme. | `ADMIN_RESOLVED_PRIMARY` and admin CSS vars. |
| **Favicon** | `base.html` and `portal_base.html`: `<link rel="icon" href="{{ SITE_FAVICON_URL|default:'/static/favicon.ico' }}">`. | N/A |

## CSS variable

- Use **`var(--school-primary)`** for buttons, links, and active states so all surfaces respect the school’s primary color.
- Set once in design-tokens.css (default) and overridden in base/portal_base/backend_base when SITE or theme is available.
