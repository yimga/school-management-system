# Site Settings UX Changes – Summary

All changes made to make the Site Settings admin page easier to use. Site Settings is the Django admin change form at **`/admin/siteconfig/sitesettings/1/change/`**.

---

## 1. Sticky Save Bar (B3.4)

- **What:** The Save / Save and continue editing row stays visible at the bottom of the viewport while scrolling the long form.
- **Where:** `templates/admin/siteconfig/sitesettings/change_form.html` (inline styles).
- **Scope:** Scoped to Site Settings only via `body.app-siteconfig.model-sitesettings.change-form #content .submit-row`, so other admin change forms are unaffected.
- **Details:** Sticky bar uses design tokens (`--admin-content-bg`, `--admin-content-border`), top border, light shadow, and `z-index: 100`.

---

## 2. Theme & Color Side-by-Side Layout (B4)

- **What:** The “Theme & color” block is a **two-column grid**: left = theme/color tools, right = live preview. No more scrolling past the whole form to see tools and preview together.
- **Where:** `templates/admin/siteconfig/sitesettings/change_form.html` – `{% block after_field_sets %}`.
- **Left column:** “Theme & color” heading, **Revert to saved** button, Color Palette Studio, Admin Dashboard Palette Selector, Admin Theme Preset.
- **Right column:** Theme Preview Section (small-screen preview card).
- **Responsive:** At viewport width &lt; 992px, the grid becomes a single column (stacked).

---

## 3. Revert to Saved (F14)

- **What:** A **“Revert to saved”** button restores all theme/color form fields to their **saved (page-load) values** without saving the form. Useful after experimenting with colors.
- **Where:** Same template; button id `#theme-revert-to-saved`; snapshot/revert logic in inline `<script>`.
- **Fields reverted:** `primary_color`, `accent_color`, `background_color`, `header_bg_color`, `footer_bg_color`, `success_color`, `warning_color`, `danger_color`.
- **Feedback:** If any value was reverted, `window.showToast('Theme colors reverted to saved values', 'success', 2500)` is called (toast appears top-right).
- **Dark mode:** Button has dedicated dark-mode styles in the same template.

---

## 4. On/Off Badges for Critical Toggles (B5-style)

- **What:** Important boolean fields show a compact **“On”** / **“Off”** badge next to the label so admins can scan state quickly.
- **Where:**
  - **Form:** `apps/siteconfig/forms.py` – in `SiteSettingsForm.__init__`, the listed critical toggles get the class `settings-toggle-critical` (in addition to `form-check-input`).
  - **CSS:** `templates/admin/siteconfig/sitesettings/change_form.html` – `.form-check-input.settings-toggle-critical + .form-check-label::after` shows “Off” (gray pill) or “On” (green pill when checked).
- **Critical toggles:** `maintenance_mode`, `enable_parent_portal`, `enable_teacher_portal`, `enable_reports_pdf`, `report_downloads_enabled`, `use_dark_mode`, `preview_mode_enabled`.

---

## 5. Graceful Degradation When JavaScript Is Off (F13)

- **What:** If JavaScript is disabled, the page still explains what to do and the form remains usable.
- **Color Palette Studio:** `templates/admin/components/color_palette_studio.html` – `<noscript>` block with a message: “Color Palette Studio requires JavaScript. Use the color inputs in the form above to change theme colors.”
- **Theme Preview:** `templates/admin/components/theme_preview_section.html` – `<noscript>` block: “Theme preview requires JavaScript. Use the form fields to change colors; save to see changes on the site.”
- **Dark mode:** Noscript alert on Site Settings has dark-mode styles in `change_form.html`.

---

## 6. Success Feedback – Toasts (F4)

- **What:** Reusable toast component included in the admin base so any admin page can show success/error/warning/info messages. On Site Settings, **Revert to saved** uses it for success feedback.
- **Where:** `templates/components/toast_notifications.html`; included in `templates/admin/base_site.html`. API: `window.showToast(message, type, duration)`.
- **Used on Site Settings:** Revert button calls `showToast('Theme colors reverted to saved values', 'success', 2500)`.

---

## 7. Accessibility & Discoverability

- **Skip link:** Admin base includes “Skip to main content”; from the QA doc, keyboard users can Tab to it first. Helps reach main content (and thus the long Site Settings form) without tabbing through the whole sidebar.
- **Keyboard shortcuts modal:** Documents how to reach Site Settings and use Revert (e.g. from backend dashboard, pressing **?** opens the shortcuts modal).
- **i18n:** Strings such as “Theme & color”, “Revert to saved”, “Restore theme/color fields to their saved values.”, and the noscript messages are wrapped in `{% trans %}` in the Site Settings change form and included components.

---

## 8. Dark Mode Parity (F12)

- **What:** All new Site Settings–specific UI respects dark theme so it stays readable and consistent.
- **Styled for dark mode in Site Settings template:**
  - Theme revert button (`#theme-revert-to-saved`) – border and text color; hover background/border.
  - Noscript `.alert-info` – background, border, text using admin dark variables (`--admin-sidebar-surface`, `--admin-content-accent`, `--admin-content-text`).
- **Selectors:** Both `:root[data-theme="dark"]` and `html[data-bs-theme="dark"]` are used so it works with the project’s theming.

---

## 9. Assets and Components Used on Site Settings

| Asset / component | Purpose |
|-------------------|--------|
| `admin/components/theme_preview_assets.html` | Scripts/styles needed for the theme preview. |
| `admin/components/color_palette_studio.html` | Color Palette Studio (base color, presets, harmony types, apply to form). |
| `admin/components/admin_dashboard_palette_selector.html` | Preset dashboard palettes (cards). |
| `admin/components/admin_theme_preset.html` | Theme preset selector. |
| `admin/components/theme_preview_section.html` | Small-screen preview card (sidebar + cards + role selector). |

---

## 10. Additional Improvements (Done)

- **Tabs for fieldsets (B3.1):** Implemented. Every fieldset has `"classes": ("tab",)` so Unfold renders them as tabs; no long scroll.
- **“At a glance” summary tab:** First tab shows a read-only summary: site name, logo, primary color swatch, and key toggles (Maintenance, Parent portal, Teacher portal, Reports PDF, Dark mode) so the admin sees current state quickly.
- **Unsaved changes warning:** If the form is modified and the user tries to leave (close tab, navigate away), the browser shows “You have unsaved changes.” On submit, the warning is cleared.
- **Fewer tabs:** “Preview & Draft” and “System Behavior” merged into “Preview & system”; “Admin Portal” and “Portal Content” merged into “Portal & content.”
- **Collapsed long sections:** “Backend Orchestration & Limits” and “Analytics Defaults” use `"collapse"` so they are collapsed by default in the tab; expand when needed.
- **Theme block id:** The Theme & color block has `id="theme-color-tools"` for deep-linking or “Jump to Theme tools” later.

## 11. What Was Not Done (Optional Later)

- **Full-page iframe preview (B4.2 Option B):** Not implemented. Only the existing “Small screen preview” is used in the right column.

---

## Quick Reference – Where to See It

1. Open **`/admin/siteconfig/sitesettings/1/change/`** (log in as staff if needed).
2. Scroll past the fieldsets to the **“Theme & color”** block: two columns (tools left, preview right).
3. Use **“Revert to saved”** after changing a color – toast should appear; colors revert to saved values.
4. Scroll the form – the **Save** bar stays fixed at the bottom.
5. Check critical toggles (e.g. Maintenance mode, Enable parent portal) – they show **On** / **Off** badges.
6. Toggle dark mode (if your admin supports it) – revert button and noscript area should follow dark theme.

For full implementation and QA context, see **`docs/MASTER_PLAN_IMPLEMENTATION_QA.md`** and **`docs/DASHBOARD_AND_ADMIN_MASTER_PLAN.md`** (B3, B4, Part F).
