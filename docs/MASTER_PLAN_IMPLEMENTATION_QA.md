# Master Plan Implementation – QA Summary

Implementation of the Dashboard & Admin Master Plan (batches 1–10) is complete. This document summarizes what was done and lists **gaps and issues** to address.

---

## Where to see the changes on the dev server

1. **Restart the dev server** so it loads the latest code: stop it (Ctrl+C in the terminal), then run `python manage.py runserver`.
2. **Hard-refresh the browser** so CSS/JS are not cached: **Ctrl+Shift+R** (or **Ctrl+F5**). If needed, clear the site’s cache in browser settings.
3. **Open these URLs** (with a logged-in user where required):

| What to check | URL | What you should see |
|---------------|-----|---------------------|
| **Theme & color, Revert, Toast** | `/admin/siteconfig/sitesettings/1/change/` | After scrolling past the form fields: **Theme & color** heading, **Revert to saved** button, two columns (Color Studio + palette selector on the left, Small screen preview on the right). Change a color, click **Revert to saved** → a green **toast** appears top-right. Sticky **Save** bar at bottom. |
| **Skip link** | `/admin/` or `/backend/` or `/portal/` | Press **Tab** once: focus goes to **Skip to main content** link (visible when focused). |
| **Portal sidebar collapse** | `/portal/parent/` or `/teacher/` (portal layout) | Sidebar has a **collapse** control; when collapsed, only icons show; hover a nav item to see its **tooltip**. |
| **Back buttons** | Any list/detail under `/backend/` (e.g. Students, Invoices) | **Back to …** link with arrow, styled as primary/secondary/outline. |
| **Keyboard shortcuts** | `/backend/` (if modal is included) | Press **?** to open the shortcuts modal; it mentions Site Settings and Revert. |
| **Empty state** | Any page that uses `dashboard_empty_state.html` | Centered empty state with icon, title, message, optional CTA (design tokens + dark mode). |

**Note:** The **toast** and **Revert to saved** only appear on **admin** pages (Site Settings). The toast component is included in `admin/base_site.html`, so it is available on every admin page; the revert button and toast trigger exist only on the Site Settings change form.

---

## Implemented

### Part A: Dashboard Clean & Classy
- **A1 Tokens:** Dashboard tokens added in `design-tokens.css`: `--dashboard-card-radius`, `--dashboard-card-shadow`, `--dashboard-card-border`, `--dashboard-gap-*`, `--dashboard-title-size`, `--dashboard-section-size`, `--dashboard-card-title-size`; dark-mode variants for shadow/border.
- **A2 Card system:** Cards use tokens for radius, shadow, border, and body padding in `dashboard-high-contrast.css`.
- **A3 Spacing/layout:** Comfortable gutters (1rem) by default; `.dashboard-layout-compact` for tight layout.
- **A4 Typography:** Page/section/card title sizes wired to tokens in `dashboard-high-contrast.css` and `dashboard-charts.css`.
- **A5–A8:** Sidebar polish (collapsible), chart card padding/title from tokens, button/color restraint via existing CSS.
- **A9–A10:** Content/copy and responsive left as-is; theme-color layout is responsive (stack on &lt;992px).

### Part B: New Requirements
- **B1 Collapsible portal sidebar:** Toggle in `partials/portal_sidebar.html`; collapsed state (64px, icon-only) in `portal-layout-professional.css`; preference in `localStorage` key `portal-sidebar-collapsed`; resize handle hidden when collapsed.
- **B2 Back buttons:** `.btn-back-primary`, `.btn-back-secondary`, `.btn-back-outline` in `design-system-unified.css`; 25+ templates updated to use them with arrow icon and consistent placement.
- **B3 Site Settings:** Sticky Save bar on Site Settings change form (`#content .submit-row`). Full tabs/accordions for fieldsets **not** implemented (would require custom change_form or JS grouping).
- **B4 Theme & color side-by-side:** Site Settings `after_field_sets` restructured: left column = Color Palette Studio + Admin Dashboard Palette Selector + Admin Theme Preset; right column = Theme Preview Section; two-column grid with single-column fallback at 992px.
- **B5 Toggle & button color coding:** `toggle-colors.css` extended for backend dark body; `.btn-state-on` / `.btn-state-off` and back-button classes added. Toggle-colors already loaded in base, portal_base, admin.
- **B6 Color Harmony types:** In `color-harmony-engine.js`: added `square`, `achromatic`, `polychromatic`, `diad`; registered in `HARMONIES` and public API. Color Palette Studio shows them via `listHarmonies()`.

---

## QA Checks Performed

- **Django:** `python manage.py check` – no issues.
- **Tests:** `apps.siteconfig.tests.test_feature_control` – 4 tests passed.

---

## Resolved (Follow-up Completed)

- **Gap 1 (Sticky Save bar scope):** Selector narrowed to `body.app-siteconfig.model-sitesettings.change-form #content .submit-row` so only Site Settings gets the sticky bar.
- **Gap 2 (Portal sidebar tooltips):** `title` attributes added to portal sidebar nav links for collapsed state.
- **Gap 8 (Accessibility – Part F):** Skip links added to `base.html`, `admin/base_site.html`, and portal; keyboard shortcuts modal documents sidebar and Site Settings.
- **Gap 9 (Manual / E2E):** Step-by-step manual testing instructions added below.
- **Gap 10 (i18n):** New UI strings wrapped in `{% trans %}` where applicable (e.g. Theme & color, Revert to saved, noscript messages).
- **Part F – Theme undo/revert (F14):** "Revert to saved" button added on Site Settings; restores theme/color form fields to page-load (saved) values.
- **Part F – Graceful degradation (F13):** `<noscript>` fallback messages added for Color Palette Studio and Theme Preview; form fields remain usable when JS is disabled.
- **Part F – Loading/empty states (F2):** Enhanced `dashboard_empty_state.html` component with improved styling, dark mode support, and design token usage. Reusable across dashboards.
- **Part F – Success/error feedback (F4):** Created reusable `toast_notifications.html` component with `window.showToast()` API. Supports success/error/warning/info types, auto-dismiss, manual close, and dark mode. Included in admin base template.
- **Part F – Dark mode parity (F12):** Added dark mode styles for theme revert button, noscript alerts, empty states, and toast notifications. All new components respect `data-theme="dark"` and `data-bs-theme="dark"`.
- **Part F – Breadcrumbs (F3):** Breadcrumb components already exist (`components/breadcrumb.html`, `partials/breadcrumbs.html`) and are used consistently across admin, backend, and portal. Both support `BREADCRUMBS` context variable and auto-generation from URL path. Placement is consistent (below header, above title).

---

## Gaps and Issues to Address

### 1. **Sticky Save bar scope** *(resolved – see Resolved section)*
- Sticky bar uses selector `#content .submit-row`, so it applies to **all** admin change forms, not only Site Settings. If other forms have a submit row, they will also get a sticky bar. Consider narrowing to Site Settings only (e.g. by adding a wrapper id/class in the Site Settings change form template and targeting that).

### 2. **Portal sidebar collapse: tooltips** *(resolved)*
- Collapsed sidebar shows icons only; nav link labels are hidden. `title` attributes were added to portal sidebar nav links for hover tooltips when collapsed.

### 3. **Portal sidebar collapse: mobile**
- Collapse toggle is `d-none d-lg-block`; on mobile the sidebar is offcanvas. No change to mobile behavior. Confirm offcanvas open/close and focus management are still acceptable.

### 4. **Back button templates not updated**
- The following were not changed (navbar brand “Back to home” links, or single instances): `portal_base.html` (navbar brand), `admin/base_site.html` (toolbar “Back to dashboard”), `components/admin_nav_bridge.html` (“Back to Backend”). These are either navigation chrome or already consistent; you may still want to apply `.btn-back-*` where it fits.

### 5. **Site Settings: tabs/accordions**
- B3.1 (group fieldsets into tabs or accordions) was **not** implemented. The form is still one long page with a sticky Save bar. Implementing would require a custom admin change_form template or JS that wraps Django-rendered fieldsets.

### 6. **Color Studio / Preview: full-page iframe**
- B4.2 Option B (iframe with preview URL) was **not** implemented. Only the existing “Small screen preview” is in the right column. Add later if you want a full-page live preview.

### 7. **Design tokens: usage**
- Some dashboard pages may still use hardcoded spacing or font sizes instead of `--dashboard-*` tokens. A follow-up pass could grep for `1rem`, `1.5rem`, `12px`, etc. in dashboard CSS/templates and replace with tokens where appropriate.

### 8. **Accessibility**
- Part F (e.g. focus trap in modals, skip link, keyboard nav for sidebar) was **not** implemented. Recommended as a separate pass.

### 9. **Manual / E2E** *(instructions added)*
- Use the steps below for manual or E2E testing. Automated pa11y can be run on the listed URLs.
- **Manual testing steps:**
  1. Start dev server: `python manage.py runserver`
  2. Open in browser: `/`, `/backend/`, `/admin/`, `/portal/parent/`, `/teacher/`. Then go to **Admin → Site configuration → Site settings** (Site Settings) and **Feature Control** (if available).
  3. **Portal sidebar:** On portal pages, use the collapse toggle; confirm icon-only state and tooltips on nav links; confirm resize (if applicable).
  4. **Back buttons:** On list/detail pages, confirm "Back to …" buttons use the expected style (primary/secondary/outline) and arrow icon.
  5. **Site Settings:** Confirm sticky Save bar; Theme & color two-column layout; Color Palette Studio (base color, harmony type, Apply palette); Admin theme preset; "Revert to saved" restores color fields; small screen preview updates when colors change. With JS disabled, confirm noscript fallback messages for Color Studio and preview.
  6. **Accessibility:** Use Tab to reach "Skip to main content"; confirm focus order. Run pa11y (or your a11y tool) on key URLs, e.g. `/`, `/backend/`, `/admin/`, `/admin/siteconfig/sitesettings/1/change/`.

### 10. **i18n** *(resolved)*
- New UI strings (e.g. Theme & color, Collapse sidebar, Revert to saved, noscript messages) are wrapped in `{% trans %}` where applicable.

---

## Files Touched (Summary)

- **CSS:** `design-tokens.css`, `toggle-colors.css`, `design-system-unified.css`, `dashboard-high-contrast.css`, `dashboard-charts.css`, `portal-layout-professional.css`
- **JS:** `color-harmony-engine.js`
- **Templates:** `portal_base.html`, `partials/portal_sidebar.html`, `admin/siteconfig/sitesettings/change_form.html`, `admin/base_site.html`; 25+ templates for back buttons (parent, portal, finance, evals, analytics, accounts, siteconfig, staff, people, reports, requests); `components/toast_notifications.html`, `components/dashboard_empty_state.html` (enhanced)
- **Docs:** This file (`docs/MASTER_PLAN_IMPLEMENTATION_QA.md`)

---

## Step-by-step implementation (completed)

1. **Phase 1 – Harmony engine:** Implemented missing `square`, `achromatic`, `polychromatic`, `diad` in `color-harmony-engine.js`; added `nearComplementary`, `neutralWithAccent`, `commonComponent`, `contrastLightDark`, `hueContrast`, `ostwaldGrey`, `warmPalette`, `coolPalette`, `earthTones`. Color Palette Studio shows all via `listHarmonies()`.
2. **Phase 2 – Toggle/button color:** All Site Settings boolean fields now get `settings-toggle-critical` (On/Off badges). `toggle-colors.css` already loaded in admin/base_site.html.
3. **Phase 3 – Back buttons:** Admin toolbar “Back to dashboard” and admin_nav_bridge “Back to Backend” now use `btn-back-outline`.
4. **Phase 4 – Sidebar:** Verified: backend extends portal_base, so backend uses the same collapsible portal sidebar; admin uses Django/Unfold collapsible sidebar.
5. **Phase 5 – Site Settings tabs:** All Site Settings fieldsets have `"classes": ("tab",)` so Unfold renders them as fieldset tabs (no long scroll).
6. **Phase 6 – Preview doc:** Added `docs/PREVIEW_SYSTEM.md` describing small-screen preview, toggle_preview_mode, customizer, and how to add full-page preview later.

---

## Next Steps

1. Manually test key flows (Site Settings tabs, harmony types, toggles, back buttons) and run pa11y on critical URLs.
2. Optionally: B4.2 Option B (iframe full-page preview), Part F (accessibility) in a follow-up.
