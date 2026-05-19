# Theme System

This document describes how light/dark theme is applied across the three surfaces: Admin, Backend, and Portal. All theme work should respect this architecture.

## 0. HTML attribute contract (v3, 2026-05-18)

The platform writes four theme-related attributes on `<html>`. CSS rules must read the **effective** attributes, not the preference, or system-preference users with dark OS see white-text-on-white-card across every dashboard.

| Attribute | Value space | What it means | When to read in CSS |
|---|---|---|---|
| `data-theme` | `light` \| `dark` | **Effective** theme. Always one of two values. | Use this for all light/dark styling rules. |
| `data-resolved-theme` | `light` \| `dark` | Same as `data-theme`; kept for sites that adopted it during v2. | Equivalent to `data-theme`. |
| `data-bs-theme` | `light` \| `dark` | Bootstrap 5 compat. Mirrors effective. | Use for Bootstrap-derived utilities. |
| `data-theme-preference` | `light` \| `dark` \| `system` | The raw user preference. May be `system`. | **Toggle UI / preference UX only.** Never gate styling on this. |

Bootstrap script: [`static/js/theme-preference-bootstrap.js`](../static/js/theme-preference-bootstrap.js). The legacy `static/js/_pages/base.js` follows the same contract.

CI guard: [`scripts/scan_theme_attribute_contract.py`](../scripts/scan_theme_attribute_contract.py) (zero-tolerance) flags CSS selectors that bind styling to `[data-theme="system"]` (a no-op under v3) and JS callers that write `system` into `data-theme`.

### Why this matters (the v2 → v3 fix)

Under v2, `data-theme` carried the raw preference (`light` / `dark` / `system`). A user with preference="system" + OS=dark got `<html data-theme="system">`, which never matched any `[data-theme="dark"]` rule. Aesthetic-profile dark overrides like `[data-rmc-aesthetic="cool-apple"][data-theme="dark"]` set `--surface-elevated: #1e293b`; under the broken contract these never fired, so cards stayed white. Meanwhile `[data-bs-theme="dark"]` *did* match (Bootstrap path), so `--text-primary` flipped to near-white. Net effect: **white text on white card platform-wide** — the symptom that triggered this fix. v3 collapses `data-theme` to the effective value; 271 CSS sites across 34 files start matching correctly with zero CSS edits.

## 0.1 Dual-plane theme & experience (tenant vs manager)

RunMyCampus exposes **two independent configuration planes** for look-and-feel:

| Plane | Host | Hub URL | Who |
| --- | --- | --- | --- |
| **Tenant / school** | `https://<school>.runmycampus.com` | `/siteconfig/theme-experience/hub/` | School staff with `settings.manage` |
| **Platform / manager** | `https://manager.runmycampus.com` | `/siteconfig/theme-experience/hub/` | Control-plane operators (superuser / SUPERADMIN) |

- **Tenant hub** links to Studio Experience, Theme & Experience editor, admin/backend theme pack, dashboards, compare/recommendations, and School Configuration Center — all scoped to **one school**.
- **Manager hub** links to platform Studio, Theme & Experience editor, `/configuration/experience/`, RuntimeDefaults **public brand** (manager chrome colors/logos), and Platform global branding. Per-school work uses **Open as school** from the schools registry (tenant host), not manager defaults alone.
- Legacy `/siteconfig/theme-experience/` redirects to the **hub**; append `?studio=1` to jump directly to Studio Experience (old bookmarks).

Operator manager chrome reads `RuntimeDefaults.public_brand_*` via `CONTROL_PLANE_BRAND_CSS_VARS` on `control_plane_skeleton.html` (`static/css/control-plane-operator-brand.css`).

Gate: `python scripts/verify_dual_plane_theme_experience.py`.

## 1. Three surfaces

| Surface | Base template | Theme source | Where theme is applied |
|--------|----------------|--------------|-------------------------|
| **Admin** (`/admin/`) | Unfold → `templates/admin/base_site.html` → `templates/admin/admin_dashboard.html` | `SITE.admin_sidebar_*` in `:root`; dashboard toggle uses **`localStorage.runmycampus-theme-preference`** and sets `data-theme` + `data-bs-theme` on `<html>` | Sidebar: `static/css/admin_sidebar_enhanced.css` (`:root`, `:root[data-theme="light"]`, `:root[data-theme="dark"]`, `html[data-bs-theme="light"]`, `html[data-bs-theme="dark"]`). Dashboard has inline `:root` / `:root[data-theme="dark"]` and a theme button. |
| **Backend** (`/authentication/backend/`) | `templates/portal_base.html` → `templates/backend_base.html` → backend dashboard | `SITE.backend_console_theme` (default `'dark'`) | Inline script on DOMContentLoaded sets `data-theme` and `data-bs-theme` on `<html>`, adds `portal-backend-dark` or `portal-backend-light` to `<body>`. `static/css/backend-dark-theme.css` and `static/css/backend-light-theme.css` target `body.portal-backend-*`. |
| **Portal** (parent/teacher dashboards) | `templates/portal_base.html` | **`localStorage.runmycampus-theme-preference`** (default `"light"`) | Inline script in head and DOMContentLoaded/cycleTheme in portal_base; `static/js/phase7-theme.js` uses same key. Both set `data-theme` and `data-bs-theme` on `<html>`. `static/css/portal-theme-modes.css` uses `html[data-bs-theme="dark"]`. |

Admin and Portal share the same localStorage key (`runmycampus-theme-preference`) so the user’s theme choice follows them between portal and admin. Backend is server-driven and overrides portal when on backend routes.

## 2. Shared CSS stack (load order)

Load order matters. Use this order where applicable:

1. **`static/css/design-tokens.css`** – Shared variable names (`--school-primary`, `--admin-sidebar-*`, `--portal-*`, `--backend-*`). Loaded by admin (base_site), portal (portal_base), and thus backend.
2. **`static/css/design-system-unified.css`** – Palette and spacing (`--color-primary`, `--color-text-primary`, radius, shadows). Used by admin and portal. Templates can override with `SITE.*` (e.g. `--school-primary: {{ SITE.primary_color }}`).
3. **`static/css/bootstrap-theme-bridge.css`** – Documents that `data-theme` and `data-bs-theme` stay in sync; in dark mode sets Bootstrap semantic vars to match the design system. **Admin does not load this**; portal/backend can. Actual sync is done in JS (portal inline script, backend_base inline script, phase7-theme.js, admin_dashboard toggle).
4. Surface-specific CSS (e.g. `admin_sidebar_enhanced.css`, `admin-dark-readability.css`, `portal-theme-modes.css`, `backend-dark-theme.css`).

Admin does **not** load `bootstrap-theme-bridge.css` or `phase7-theme.js`; it uses base_site + admin_dashboard theme toggle and Unfold.

## 2.1 Platform palette (single source of truth)

- **`static/css/design-system-unified.css`** – Primary platform palette: `--color-primary`, `--color-secondary`, `--color-accent`, `--color-text-primary`, `--color-text-muted`, spacing, radius, shadows. Used by Portal and referenced where brand colours are needed.
- **`static/css/design-tokens.css`** – Shared semantic tokens: `--school-primary`, `--admin-sidebar-*`, `--portal-*`, `--backend-*`. Admin sidebar defaults are defined here for readability (WCAG-friendly); they are overridden by `templates/admin/base_site.html` when `SITE.admin_sidebar_*` is set in SiteSettings.
- **Admin sidebar recommended defaults** (when no SiteSettings overrides): sidebar bg `#0f172a`, text `#f1f5f9`, muted/section `#cbd5e1`, heading `#e2e8f0`, active border `#38bdf8`. These live in `design-tokens.css` and in `admin_sidebar_enhanced.css` `:root` and theme blocks (`:root[data-theme="light"]`, `:root[data-theme="dark"]`).

## 3. Best practices

- **One key per surface (or one key site-wide):** Portal and Admin both use `runmycampus-theme-preference` so theme preference is consistent. Backend is driven by server setting.
- **Set both attributes:** When changing theme in JavaScript, set both `data-theme` and `data-bs-theme` on `document.documentElement` so Unfold/Bootstrap and our CSS (e.g. admin_sidebar_enhanced, admin-dark-readability) stay in sync.
- **Semantic CSS variables:** Define colors in `:root` and theme blocks; use variables in components. Override accent/status in dark mode with desaturated values for readability.
- **No pure black/white in UI:** Use near-black (e.g. `#0f172a`) and off-white (e.g. `#f1f5f9`) for backgrounds and text.

## 4. Key files

| Purpose | File(s) |
|--------|--------|
| Admin base, sidebar vars | `templates/admin/base_site.html` |
| Admin dashboard theme toggle | `templates/admin/admin_dashboard.html` (toggleTheme, DOMContentLoaded) |
| Admin sidebar styles | `static/css/admin_sidebar_enhanced.css` |
| Admin list/detail readability | `static/css/admin-dark-readability.css` |
| Portal/Backend base, theme script | `templates/portal_base.html`, `templates/backend_base.html` |
| Portal theme manager | `static/js/phase7-theme.js` |
| Portal theme modes | `static/css/portal-theme-modes.css` |
| Design system + dark overrides | `static/css/design-system-unified.css` |
| Bootstrap sync (dark vars) | `static/css/bootstrap-theme-bridge.css` |

All theme-related work should happen only in the main repo (branch: improvements). No worktrees.

## 5. Admin sidebar and header (RBAC)

Admin sidebar and header structure, design tokens (`--admin-sidebar-*`), and how RBAC filters sidebar apps, model counts, and dashboard KPIs are documented in **ADMIN_UI.md**. Sidebar and header share those tokens and are permission-driven. What is configurable from the admin panel (Admin Sidebar Theme fieldset, theme pack) vs not (layout, child text), and what “complete revamp” means (theme = yes from admin; structure = no, requires code) is also in **ADMIN_UI.md** (§4).
