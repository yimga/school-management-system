# /admin Audit: What We’re Doing Well, Gaps, Improvements, Redundancy

**Scope:** Django admin at `/admin/` — templates, config (Site Settings, Region Config, Theme Pack), dashboard feel, sidebar, and theme.

---

## 1. What We’re Doing Well

- **Single Site Settings:** `SiteSettings` is a singleton; one row, no add/delete. Permission gated (`_is_site_admin`: staff + Admin/Superadmin or superuser). Clear “one place” for global config.
- **Structured fieldsets:** Site Settings admin uses logical groups: Branding, Preview & Draft, Company Details, Login/Header/Layout, Theme & Experience, **Admin Sidebar Theme** (collapse), Admin Portal, Portal Content, Footer, System Behavior, Feature Toggles, Backend Orchestration, Notifications, Compliance, Analytics Defaults, Metadata. Easy to find the right section.
- **Admin theme from Site + ThemePack:** Context exposes `SITE`, `SITE_ADMIN_THEME` (from `admin_theme_pack` or fallback), `SITE_ADMIN_BACKGROUND_URL`, `SITE_ADMIN_LOGO_URL`. Admin can use either per-model sidebar colors (SiteSettings) or a Theme Pack for admin (logo, background). Good for branding.
- **Sidebar colors in one place:** SiteSettings has a dedicated “Admin Sidebar Theme” fieldset (bg, surface, border, text, muted, hover, active, badge, child gradient, `admin_use_site_primary`). base_site.html injects these as CSS variables so the sidebar respects config.
- **Custom admin site:** `GileadAdminSite` customizes index (dashboard), app list order, and adds URLs (dashboard, activity-logs, system-health). App grouping (Accounts, People, Academics, Evals, etc.) and “System Configuration” last is clear.
- **Dashboard content:** The actual `/admin/` view uses `admin_dashboard.html` with preview status, finance inbox, security stats, login/access stats, and calendar. Useful for day-to-day ops.
- **RegionConfig:** Separate model and admin for regions (timezone, currency, grading, terms, portals). Fieldsets and inlines (grading scales, holidays) keep region config in one screen. Clone/validate/export actions exist.
- **Site Settings change form:** Uses a custom template that adds theme preview (small-screen preview, role selector, contrast hint). Helps admins see impact of theme/sidebar changes.
- **Model count badges:** base_site injects `MODEL_COUNTS` and sidebar JS adds badges per model. “Jump to model” search in sidebar improves navigation on large app lists.
- **Preview mode:** Preview & Draft fieldset and session-based preview let admins stage theme/settings without committing. Preview cue in base_site branding shows toggle/clear.

---

## 2. Gaps

| Area | Gap | Impact |
|------|-----|--------|
| **Two admin “home” templates** | `/admin/` is rendered with `admin_dashboard.html` (config/admin.py). `admin/index.html` also exists (stats grid + app grid + theme toggle) and extends base_site. It’s unclear if index.html is ever used; if not, it’s dead code. If it is (e.g. alternate route), users could see two different “admin home” UIs. | Confusion; possible dead code or inconsistent entry experience. |
| **Three sources of admin theme variables** | (1) base_site.html injects `--admin-sidebar-*` from `SITE`. (2) admin_sidebar_enhanced.css defines its own `:root` and `:root[data-theme="light"]` / `:root[data-theme="dark"]` with hardcoded fallbacks. (3) admin/index.html uses `ADMIN_THEME=SITE_ADMIN_THEME|default:SITE` and different var names (`--brand-primary`, `--surface-dark`, etc.). Overlap and naming differ. | Sidebar can ignore SiteSettings if CSS loads after base_site; light/dark toggle may not match “Admin Sidebar Theme” colors; index.html (if used) uses a different theme system. |
| **Admin dashboard doesn’t use SITE for theme** | admin_dashboard.html defines its own `:root` (e.g. `--admin-dashboard-bg`, `--admin-surface`, `--admin-accent`) with hardcoded defaults. It does not use `SITE` or `SITE_ADMIN_THEME` for these. | Dashboard content area doesn’t reflect Site Settings or Admin Theme Pack; feels disconnected from the rest of admin theming. |
| **Theme toggle in index.html only** | index.html has a theme toggle (Light/Dark) that writes to `localStorage` and body class. base_site.html has a nav-global theme toggle that uses `siteconfig:update_theme`. Admin dashboard (admin_dashboard.html) doesn’t expose a consistent theme toggle. | If user lands on admin_dashboard, they may not have the same theme control as on index or base_site nav. |
| **admin_theme_pack vs SiteSettings sidebar** | Sidebar colors come from SiteSettings (admin_sidebar_*). Admin “look” (background, logo) can come from ThemePack (admin_theme_pack). There’s no single “admin theme” that clearly says “use this pack for everything” vs “use these sidebar colors.” | Admins may not know whether to change Theme Pack or Site Settings for a given visual. |
| **RegionConfig and SiteSettings relationship** | SiteSettings has `region` (CharField) and possibly default_region; RegionConfig is separate. Default region / which region drives admin locale or formatting isn’t obvious from the admin UI. | Unclear how “region” in Site Settings relates to RegionConfig list; risk of duplicate or inconsistent region concept. |
| **Admin Portal fieldset** | “Admin Portal” contains only `admin_portal_stats_config`. No explanation in the form of what this controls or where it’s used. | Admins may skip or misconfigure it. |
| **No “Admin dashboard” section in Site Settings** | There’s “Admin Sidebar Theme” and “Admin Portal” (stats config) but no explicit “Admin dashboard layout” or “Admin index page” (e.g. which template, which widgets). | Customization of the admin home experience is implicit (code) not config. |

---

## 3. Where We Can Improve

- **Single source for admin theme variables:**  
  - Decide: base_site is the only place that outputs `--admin-sidebar-*` (and any other admin vars) from `SITE` (and optionally `SITE_ADMIN_THEME`).  
  - Change admin_sidebar_enhanced.css to **not** set `:root { --admin-sidebar-* }`; only use the variables (e.g. `background: var(--admin-sidebar-bg)`). If you need fallbacks for when context isn’t available, use a single small “admin-vars-defaults.css” that base_site can override, or use CSS custom property fallbacks in the same file (e.g. `var(--admin-sidebar-bg, #0b0f14)`).  
  - Result: one place (base_site + optional defaults) drives sidebar and, if you extend, dashboard content area.

- **Admin dashboard feel:**  
  - Make admin_dashboard.html use the same tokens as the rest of admin (e.g. `var(--admin-sidebar-surface)` for cards, or a shared set like `--admin-surface`, `--admin-border`) and source them from base_site (from `SITE` / `SITE_ADMIN_THEME`).  
  - Add a small “Admin dashboard” or “Admin content” block in base_site that sets e.g. `--admin-dashboard-bg`, `--admin-surface`, `--admin-accent` from SiteSettings or Theme Pack, so dashboard and sidebar feel like one theme.

- **Clarify index.html vs admin_dashboard.html:**  
  - If index.html is unused: remove or redirect to admin_dashboard to avoid two “home” UIs.  
  - If it’s intentional (e.g. “simple” vs “full” dashboard): document it and add a clear way to switch (e.g. link “Simple dashboard” / “Full dashboard” in nav or Site Settings).  
  - Prefer one canonical admin home and one template.

- **Theme toggle consistency:**  
  - Use the same theme toggle mechanism everywhere: e.g. the one in base_site nav (Light/Dark/System) that calls `siteconfig:update_theme`.  
  - If index.html or admin_dashboard needs a toggle, reuse that component or the same localStorage/key and class so admin always has one predictable theme control.

- **Config items clarity:**  
  - **Admin Sidebar Theme:** Add one sentence in the fieldset description: “Colors for the left sidebar on all /admin/ pages. Optional: check ‘Use site primary for active state’ to use the main site primary color.”  
  - **Admin Portal:** Add help text or short description for `admin_portal_stats_config` (e.g. “JSON config for stats shown on the admin dashboard” or “Leave blank to use defaults”).  
  - **admin_theme_pack:** In the form, add a line: “Used for admin background image and logo. Sidebar colors are set in ‘Admin Sidebar Theme’ below.”

- **Region vs RegionConfig:**  
  - In Site Settings, if there’s a “default region” or “region” field, add help text: “Display/default region. For full region settings (timezone, currency, grading), use Region configuration in System Configuration.”  
  - Optionally add a read-only link “Manage regions →” next to it pointing to RegionConfig changelist.

- **Admin dashboard layout:**  
  - Consider making the admin home content (preview card, finance inbox, security, calendar) configurable (e.g. show/hide sections via SiteSettings or a simple JSON config) so schools can hide “Finance inbox” or “Preview” if not needed.  
  - Keep the current layout as default so behavior doesn’t change until you add that config.

---

## 4. Redundancy and How to Close the Loop

| Redundancy | Where | How to close the loop |
|------------|--------|------------------------|
| **Admin sidebar variables defined twice** | base_site.html injects `--admin-sidebar-*` from `SITE`. admin_sidebar_enhanced.css defines the same names in `:root` and `:root[data-theme="light"]` / `dark`. | Remove `:root` / `:root[data-theme]` blocks from admin_sidebar_enhanced.css; keep only rules that *use* the variables. Let base_site (and one optional defaults file) define values. Use fallbacks in the CSS if needed, e.g. `var(--admin-sidebar-bg, #0b0f14)`. |
| **Admin “brand” variables in two shapes** | base_site uses `SITE` and sidebar vars. index.html uses `SITE_ADMIN_THEME|default:SITE` and `--brand-primary`, `--surface-dark`, etc. | Pick one naming and one source. Prefer base_site as the single place that sets both sidebar and “admin content” vars (from SITE + SITE_ADMIN_THEME). If index.html stays, make it use the same variable names and don’t redefine them inline. |
| **Dashboard content theme in its own bubble** | admin_dashboard.html defines its own `:root` for `--admin-dashboard-bg`, `--admin-surface`, etc. | Stop defining these in admin_dashboard. In base_site (or a shared admin layout), set “content” vars from SITE/SITE_ADMIN_THEME once. admin_dashboard extends base_site and only uses the variables. |
| **Multiple “admin” CSS entry points** | base_site loads design-system-unified, admin-components, admin_theme, admin_sidebar_enhanced, admin-dark-readability, admin-dashboard, dashboard-responsive (and admin-dashboard twice). | Keep a single list in base_site; remove duplicate admin-dashboard link. Consider one “admin.css” that imports or concatenates the rest so load order and overrides are obvious. |
| **Theme Pack for portal vs for admin** | ThemePack has `applies_to_admin`; SiteSettings has `theme_pack` (portal) and `admin_theme_pack` (admin). | Already separated; no change needed. Document in Site Settings: “Theme pack (portal)” vs “Admin theme pack (admin background/logo). Sidebar colors are below.” |
| **Preview cue and preview fieldset** | Preview & Draft fieldset (preview_mode_enabled, preview_note) vs preview cue banner in base_site. | Keep both; they serve different purposes (config vs in-page banner). Optionally add in the fieldset: “When enabled, the preview banner appears at the top of admin and portal.” |

---

## 5. Config Items Summary (Quick Reference)

| Config | Where | Purpose |
|--------|--------|--------|
| **Site Settings (single row)** | Admin → System Configuration → Site Settings | Branding, company, login/header/layout, theme colors, **Admin Sidebar Theme**, Admin Portal (stats config), portal/footer, feature toggles, backend limits, analytics defaults. |
| **Admin Sidebar Theme** | Site Settings → “Admin Sidebar Theme” (collapse) | 14 color fields + “Use site primary for active state.” Drives sidebar on all /admin/ pages (base_site injects as CSS vars). |
| **Admin Theme Pack** | Site Settings → Branding (theme_pack area) or dedicated field | `admin_theme_pack` FK. Provides admin background image and logo; fallback logic in `get_admin_theme()`. |
| **RegionConfig** | Admin → System Configuration → Region configuration | Per-region: timezone, currency, grading scale, terms, portals; inlines for grading scales and holidays. |
| **Theme & Experience** | Site Settings → “Theme & Experience” | primary/accent/success/warning/danger, theme_brightness, use_dark_mode, **backend_console_theme** (Backend Console, not Django admin), fonts, base font size, default widgets, report defaults, default_dashboard_view, refresh_rate. |
| **Preview & Draft** | Site Settings → “Preview & Draft” | preview_mode_enabled, preview_note. Session-based staging of theme/settings. |
| **admin_portal_stats_config** | Site Settings → “Admin Portal” | JSON; used for admin dashboard stats/config. Not documented in UI. |

---

## 6. Dashboard Feel (Current vs Suggested)

- **Current:**  
  - `/admin/` renders admin_dashboard.html (preview card, finance inbox, security stats, calendar, etc.) with its own `:root` and no use of SITE/SITE_ADMIN_THEME for that content.  
  - Sidebar comes from base_site + admin_sidebar_enhanced and *does* use SiteSettings sidebar colors.  
  - So: sidebar = configurable; main content area = hardcoded theme.

- **Suggested:**  
  - **One theme for all of admin:** base_site (or one shared admin base) sets both sidebar and content variables from SITE + SITE_ADMIN_THEME.  
  - **One admin home:** Either admin_dashboard.html only, or index.html only, with a clear note in docs/code.  
  - **Same theme toggle:** Use the base_site nav theme toggle everywhere so Light/Dark/System is consistent.  
  - **Optional:** “Admin dashboard” section in Site Settings (or a tiny JSON config) to show/hide sections (preview, finance inbox, security, calendar) so the dashboard feel is configurable without code.

---

## 7. Suggested Order of Work (Admin-Only)

1. **Single source for sidebar vars**  
   Remove duplicate `:root` / `:root[data-theme]` from admin_sidebar_enhanced.css; keep only rules that use the variables. Rely on base_site (and optional fallbacks) so “Admin Sidebar Theme” is the only source of truth.

2. **Clarify index.html vs admin_dashboard.html**  
   Decide which is the canonical admin home; remove or redirect the other, and document the choice.

3. **Drive admin dashboard theme from config**  
   In base_site (or shared admin base), set `--admin-dashboard-bg`, `--admin-surface`, `--admin-accent`, etc. from SITE / SITE_ADMIN_THEME. Update admin_dashboard.html to use these vars only (no local `:root`).

4. **Config copy and help**  
   Add short descriptions for “Admin Sidebar Theme,” “Admin Portal” (`admin_portal_stats_config`), and `admin_theme_pack` so admins know what each controls.

5. **Theme toggle**  
   Ensure the same toggle (e.g. base_site nav) is used across admin; remove or align any duplicate toggle in index.html.

6. **Optional**  
   Add a small “Admin dashboard” config (e.g. show/hide sections) in Site Settings and use it in admin_dashboard.html so dashboard feel is configurable.

---

*This audit focuses only on `/admin/`. It aligns with the platform game plan (single source for theme, no redundancy, clear config) and can be merged into the main game plan as “Admin” subsection.*
