# Detailed Implementation Plan – Sidebars, Back Buttons, Site Settings, Color & Harmony

This document answers: **Was the previous work complete?** and provides a **detailed plan** so we can decide how to proceed on each area. It maps your requirements to current state, gaps, and concrete steps.

---

## 1. Completion Status Overview

| Area | What’s done | What’s not done |
|------|-------------|------------------|
| **Sidebar collapsible** | Portal/backend/parent/teacher sidebar has collapse (toggle, icon-only, localStorage, tooltips). Admin sidebar is already collapsible (Django). | Verify backend_base and any other layout that shows a sidebar; ensure collapse works and is visible on all those layouts. |
| **Back buttons** | 25+ templates use `.btn-back-primary`, `.btn-back-secondary`, `.btn-back-outline` with arrow icon. | A few places (navbar brand, admin “Back to dashboard”, admin_nav_bridge “Back to Backend”) don’t use the semantic classes; some detail pages may still lack a back button. |
| **Site Settings** | Sticky Save bar, Theme & color side-by-side (tools left, preview right), Revert to saved, On/Off badges for critical toggles, noscript/toast/dark mode. | Form is still one long page (17 fieldsets). No tabs/accordions (B3.1). No summary fieldset at top (B3.3). |
| **Color Studio / Picker / ThemePacks** | Layout consolidated: Theme & color block with Studio + palette selector + theme preset (left) and small-screen preview (right). Studio applies to form fields. | Theme & Experience **fieldset** is still above this block (admin renders fieldsets first, then `after_field_sets`). No full-page iframe preview (B4.2 Option B). |
| **Button/toggle color coding** | `toggle-colors.css`: form-switch ON=green, OFF=grey (admin, portal, backend). Site Settings critical toggles have On/Off badges. Feature Control has status badges (On/Off). | Not every Site Settings boolean has `settings-toggle-critical`; ensure toggle-colors loads on admin; align all toggles with Feature Control pattern (green/grey, badges where useful). |
| **Harmony types** | Engine has: complement, splitComplementary, triadic, analogous, monochromatic, tetradic. **HARMONIES** also lists square, achromatic, polychromatic, diad but **their functions are not implemented** (will break when selected). | Implement missing square, achromatic, polychromatic, diad; then add new types from your list (see Section 7). |

---

## 2. Sidebar – Make All Users’ Sidebar Collapsible Like /admin

### Current state
- **Admin (`/admin`):** Django admin sidebar is collapsible (e.g. `#nav-sidebar.sidebar-collapsed`, toggle, icons only).
- **Portal/Backend/Parent/Teacher:** `partials/portal_sidebar.html` is used inside `portal_base.html`; collapse is implemented:
  - Toggle button, class `portal-sidebar-collapsed` on `#portal-sidebar-col`, localStorage key `portal-sidebar-collapsed`, tooltips on nav links when collapsed.
  - CSS in `portal_base.html` (and/or `portal-layout-professional.css`) for narrow width, icon-only.
- **Backend:** Backend dashboard and list/detail pages may use `backend_base.html` or extend `portal_base.html`; need to confirm which layout shows the sidebar and that it’s the same portal sidebar.

### Gaps
1. Confirm every layout that shows a left sidebar uses the same collapsible mechanism (portal sidebar or admin sidebar).
2. If any layout has a different sidebar (e.g. backend_base with its own nav), add collapse there too (same UX: toggle, icon-only, persist).
3. Mobile: collapse toggle is often hidden on small screens; offcanvas is used. Confirm offcanvas open/close and focus are acceptable.

### Plan

| Step | Action | Notes |
|------|--------|--------|
| 2.1 | **Audit layouts** | List all base templates that include a sidebar: `admin/base_site.html`, `portal_base.html`, `backend_base.html`, others. For each, note which partial or structure provides the sidebar. |
| 2.2 | **Ensure portal sidebar is used everywhere for app UI** | Where backend/parent/teacher pages use a sidebar, ensure they use `portal_base.html` (or include `partials/portal_sidebar.html`) so one collapsible implementation covers all. |
| 2.3 | **If a layout has its own sidebar** | Add the same pattern: toggle button, class for collapsed state, CSS for narrow/icon-only, localStorage (e.g. `backend-sidebar-collapsed`), and `title` on links for tooltips when collapsed. |
| 2.4 | **Optional: sync preference with server** | If `DashboardUserPreference` or similar has a `sidebar_collapsed` field, load/save it so preference is consistent across devices (otherwise localStorage is enough). |
| 2.5 | **Mobile** | Keep offcanvas for small screens; ensure collapse toggle is only shown on desktop (e.g. `d-none d-lg-block`) and document in QA. |

**Deliverable:** Every user-facing sidebar (admin and portal/backend/parent/teacher) is collapsible with the same UX (toggle, icon-only, persist, tooltips).

---

## 3. Back Buttons – Appropriate Location, Color-Coded

### Current state
- **CSS:** `.btn-back-primary`, `.btn-back-secondary`, `.btn-back-outline` in `design-system-unified.css`; mapped to primary (e.g. blue), secondary (grey), outline.
- **Usage:** Many templates already use these classes with “Back to …” and arrow icon (e.g. `feature_control_audit`, `parent/finance`, `finance/payments`, `evals/grade_approval_detail`, `accounts/mfa_setup`, etc.).
- **Convention:** Back to **dashboard/home** → primary; back to **list/parent section** → secondary; back to **admin/config** → outline.

### Gaps
1. **Nav chrome:** `portal_base.html` (navbar brand) and `admin/base_site.html` (“Back to dashboard”) and `components/admin_nav_bridge.html` (“Back to Backend”) don’t use `.btn-back-*`; they’re navigation identity links. Decision: either leave as-is or add the class for visual consistency.
2. **Missing back buttons:** Some detail or child pages might still lack a back button (e.g. certification session detail, document edit, invoice detail). Need a short audit.
3. **Placement:** Standard is first element in main content or after breadcrumbs; a few pages may have back button in a different position.

### Plan

| Step | Action | Notes |
|------|--------|--------|
| 3.1 | **Audit all “back” links** | Grep for “Back to”, “back to”, `btn-back-`. For each template: current class, target URL, placement. List templates that are detail/child pages but have no back link. |
| 3.2 | **Apply color coding consistently** | Back to dashboard/home → `btn-back-primary`. Back to list/parent section → `btn-back-secondary`. Back to admin → `btn-back-outline`. Use same pattern: `<a href="..." class="btn btn-sm btn-back-primary"><i class="bi bi-arrow-left me-1"></i>Back to X</a>`. |
| 3.3 | **Add back button where missing** | For each detail/child page without one, add a back button with correct target and class (primary/secondary/outline). |
| 3.4 | **Optional: nav chrome** | If desired, add `btn-back-outline` (or secondary) to admin “Back to dashboard” and “Back to Backend” links so all back-style links share the same design system. |
| 3.5 | **Document** | Short note in docs or in code: when to use primary vs secondary vs outline for back buttons. |

**Deliverable:** All pages that should have a back button have one in an appropriate place, color-coded by intent.

---

## 4. Site Settings Page – Easier Administration (Large Page)

### Current state
- **17 fieldsets:** Branding, Preview & Draft, Company Details, Login/Header/Layout, Theme & Experience, Admin Portal, Portal Content, Footer Content, System Behavior, Feature Toggles, Backend Orchestration & Limits, Notifications & Analytics, Compliance & Payroll, Analytics Defaults, Metadata.
- **Already done:** Sticky Save bar (Site Settings only), Theme & color block in two columns (tools + preview) in `after_field_sets`, Revert to saved, On/Off badges for critical toggles.
- **Still:** One long vertical form; Theme & Experience **fieldset** (with color fields, theme pack, etc.) is rendered by Django above the Theme & color block, so theme editing is split between “form fields above” and “tools + preview below”.

### Gaps
1. **No tabs or accordions:** B3.1 was not implemented. The form is still one long page.
2. **No summary at top:** B3.3 was not implemented (optional “Summary” fieldset with site name, logo, primary color, link to full form).
3. **Theme editing split:** Theme & Experience fieldset is in the default fieldset list; the “Theme & color” block (Studio, palette selector, preview) is in `after_field_sets`. Improving “ease of administration” could mean grouping them visually (e.g. one tab “Theme & color” that contains both the fieldset and the block).

### Plan

| Step | Action | Notes |
|------|--------|--------|
| 4.1 | **Option A: Tabs (recommended)** | Custom change_form template (or JS) that wraps Django’s fieldset output in Bootstrap nav-tabs. Group fieldsets into 5–6 tabs, e.g. “Branding & theme”, “Company & login”, “Portal & features”, “Backend & compliance”, “Analytics & metadata”. Theme & Experience fieldset + the existing Theme & color block (Studio + preview) can live in the “Branding & theme” tab so everything theme-related is in one place. |
| 4.2 | **Option B: Accordions** | Same idea but collapsible accordion sections instead of tabs. One section open at a time (or multiple). Reduces scrolling while keeping a single form. |
| 4.3 | **Implementation approach** | Django admin renders `{% for fieldset in adminform %}`, so the template can wrap this in tab panes and add a tab list. Alternatively, use JS to group existing fieldsets by heading and add tab/accordion UI without changing admin.py structure. |
| 4.4 | **Sticky Save bar** | Keep as-is; ensure it remains visible when switching tabs (sticky to viewport). |
| 4.5 | **Optional: Summary fieldset** | Add a small “Summary” section at the very top (site name, logo, primary color) with a link “Edit full settings below” that scrolls or switches to the first tab. |

**Deliverable:** Site Settings is easier to navigate (tabs or accordions), with theme/color and preview co-located in one section.

---

## 5. Consolidate Color Palette Studio, Color Picker, ThemePacks + Preview

### Current state
- **Layout:** In Site Settings change form, `after_field_sets` contains a two-column block: left = “Theme & color” heading, Revert button, Color Palette Studio, Admin Dashboard Palette Selector, Admin Theme Preset; right = Theme Preview Section (small-screen preview). Responsive: single column below 992px.
- **Studio:** Base color, harmony types, presets, “Apply to form”; updates form fields (primary_color, accent_color, etc.).
- **Picker:** Individual fields (primary_color, accent_color, etc.) use ColorInputWithPreview (Pickr); they live in the Theme & Experience **fieldset** (above this block).
- **ThemePacks:** Model; dropdown and preset cards in the same Theme & color block.
- **Preview:** Small-screen preview only. No full-page iframe.

### Gaps
1. **Single view:** Theme & Experience **fieldset** is still rendered above by Django; the “Theme & color” block is below. So consolidation is layout-only: same page, but fieldset and block are not in one visual section unless we add tabs (Section 4) and put both in one tab.
2. **Full-page preview:** B4.2 Option B (iframe to a preview URL) was not implemented. Optional.
3. **Redundancy:** Duplicate “Color Picker” / theme descriptions in fieldset description vs block heading; can be one “Theme & color” section title.

### Plan

| Step | Action | Notes |
|------|--------|--------|
| 5.1 | **Co-locate in one section** | When tabs/accordions are implemented (Section 4), put “Theme & Experience” fieldset and the existing Theme & color block (Studio + palette selector + theme preset + preview) into one tab or accordion panel (“Theme & color” or “Branding & theme”). That gives one place for theme editing. |
| 5.2 | **Single heading** | Use one section title “Theme & color” (or “Theme & experience”); remove or shorten duplicate descriptions in the fieldset so the block heading is the main label. |
| 5.3 | **Wire Studio → form → preview** | Already in place: Studio applies to form fields; preview listens to color inputs. Verify and document that changing Studio or picker updates preview in real time. |
| 5.4 | **Optional: full-page iframe preview** | Add an optional “Open full preview in new tab” or an iframe in the right column that loads a preview URL (e.g. `/preview/` or admin index with preview mode). Requires a safe preview route and possibly same-origin or token. |
| 5.5 | **Document preview system** | Short doc: what preview exists (small-screen preview, contrast check, toggle_preview_mode), where it lives, how to add full-page preview later. |

**Deliverable:** One coherent “Theme & color” section (especially once tabs exist); Studio, Picker, ThemePacks, and preview in one place; real-time preview; optional full-page preview later.

---

## 6. Button and Toggle Color Coding (Including Site Settings, Like Feature Control)

### Current state
- **Feature Control** (`siteconfig/feature_control_panel.html`): Toggles use `form-check form-switch`; each row has a **status badge** (`bg-success` “On”, `bg-secondary` “Off”). Buttons “On” / “Off” per category use `btn-outline-success` and `btn-outline-secondary`. Clear green = on, grey = off.
- **toggle-colors.css:** Global rules for `.form-switch .form-check-input:checked` → green, `:not(:checked)` → grey; dark mode and backend dark body supported. Loaded in base, portal_base, admin (verify admin).
- **Site Settings:** Critical toggles (maintenance_mode, enable_parent_portal, enable_teacher_portal, enable_reports_pdf, report_downloads_enabled, use_dark_mode, preview_mode_enabled) get class `settings-toggle-critical` in `SiteSettingsForm` and CSS in change_form shows “On”/“Off” badge next to label. Other booleans (e.g. show_header_search, enable_entity_console) may not have the badge.

### Gaps
1. **Admin:** Ensure `toggle-colors.css` is included in `admin/base_site.html` (or the CSS that admin uses) so all form-switch toggles site-wide are green/grey.
2. **Site Settings:** Extend `settings-toggle-critical` (or equivalent) to **all** boolean fields on Site Settings so every toggle has an On/Off badge (or at least the same green/grey switch styling). Alternatively, use a single class for “all Site Settings toggles” and style them like Feature Control.
3. **Other pages:** Any form that uses checkboxes/switches for “enabled/disabled” should use `form-check form-switch` and, where it helps, a small On/Off badge (e.g. Feature Control pattern).
4. **Buttons:** Use `.btn-state-on` / `.btn-state-off` or `.btn-success` / `.btn-secondary` for actions that mean “apply/enable” vs “revert/disable” where it clarifies state (e.g. “Save” vs “Revert”).

### Plan

| Step | Action | Notes |
|------|--------|--------|
| 6.1 | **Confirm toggle-colors in admin** | Check `admin/base_site.html` (and any CSS bundle) for `toggle-colors.css`. Add if missing so admin form-switch matches Feature Control. |
| 6.2 | **Site Settings: all toggles color-coded** | In `SiteSettingsForm.__init__`, either add every BooleanField to the “critical” list that gets On/Off badge, or introduce a single class (e.g. `settings-toggle`) for all Site Settings switches and use the same CSS (On/Off badge) for all. Prefer one class so styling is consistent and themepack-independent. |
| 6.3 | **Align with Feature Control** | Use same CSS variables: `--brand-success` for on, `--color-base-300` (and dark variant) for off. Optionally add a small “On”/“Off” badge next to every Site Settings toggle (like Feature Control’s status-badge). |
| 6.4 | **Audit other forms** | Grep for `form-check-input`, `form-switch`, `type="checkbox"` in templates; ensure they use `form-check form-switch` where they represent on/off so toggle-colors applies. |
| 6.5 | **Buttons** | Where a button represents “enabled” or “applied”, use `btn-success` or `btn-state-on`; for “disabled” or “revert”, use `btn-secondary` or `btn-outline-warning`. Document in a short UI pattern note. |

**Deliverable:** All toggles (including every Site Settings boolean) color-coded green/grey; optional On/Off badges everywhere; buttons that represent state aligned with Feature Control pattern.

---

## 7. Expand Color Harmony Types (Using Your Guide)

### Current state
- **Implemented (with working functions):** complement, splitComplementary, triadic, analogous, monochromatic, tetradic.
- **Declared but not implemented (will break):** square, achromatic, polychromatic, diad — they are in `HARMONIES` and on the public API but **no `function square(hex){...}` etc. exist** in `color-harmony-engine.js`. Selecting them in the Studio will cause a runtime error.
- **Color Palette Studio:** Builds harmony buttons from `colorHarmony.listHarmonies()`; applies generated palette to form fields.

### Your categories and mapping to implementation

| Category | Type | Implementation note |
|----------|------|---------------------|
| **Fundamental geometric** | Monochromatic | Done (tints/shades/tones). |
| | Analogous | Done (2–4 adjacent). |
| | Complementary | Done (opposite). |
| | Split-Complementary | Done. |
| | Triadic | Done (120°). |
| | Tetradic (double-complementary) | Done (rectangle). |
| | Square | **Add:** 4 colors 90° apart (same as tetradic in many definitions; can be same fn or 0°, 90°, 180°, 270°). |
| **Advanced** | Achromatic | **Add:** Ignore hue; output grays (e.g. from black to white or based on input lightness). |
| | Near-Complementary | **Add:** Base + color one step (e.g. 30°) left or right of true complement. |
| | Polychromatic | **Add:** 5+ colors (e.g. 5 at 72°, or 6 at 60°); same S/L. |
| | Diad | **Add:** Two colors, e.g. base and base+60° (one “slot” on 12-part wheel). |
| | Neutral with Accent | **Add:** Achromatic base + one bold accent (e.g. grays + input hue at full saturation). |
| **Historical/scientific** | Same Hue | Same as monochromatic (already have). |
| | Common Component | **Add:** Colors “through a shared lens” — e.g. same saturation, varying hue/lightness; or tint/tone. |
| | Contrast of Light/Dark | **Add:** Same hue, opposite ends of lightness (e.g. dark + light). |
| | Hue Contrast | **Add:** Distant hues (e.g. base + 150° or 210°). |
| | Ostwald’s Grey Harmony | **Add:** 3 neutrals equally spaced in value (e.g. 3 grays). |
| **Psychological/temperature** | Warm Palette | **Add:** Reds, oranges, yellows (e.g. constrain hue range 0–60°). |
| | Cool Palette | **Add:** Blues, greens, violets (e.g. hue 180–300°). |
| | Earth Tones | **Add:** Terracotta, olive, beige — e.g. desaturated hues in warm range. |

### Plan

| Step | Action | Notes |
|------|--------|--------|
| 7.1 | **Fix broken four** | In `color-harmony-engine.js`, implement: `square(hex)` (4 colors 90° apart), `achromatic(hex)` (grays from input lightness or fixed scale), `polychromatic(hex)` (e.g. 5 colors 72° apart, same S/L), `diad(hex)` (base + base+60°). Add to HARMONIES with name/description/bestFor. |
| 7.2 | **Near-complementary** | `nearComplementary(hex)` — base + (180° ± 30°). Register in HARMONIES. |
| 7.3 | **Neutral with accent** | `neutralWithAccent(hex)` — e.g. 3–4 grays + input hue at full saturation. Register. |
| 7.4 | **Common component / contrast** | `commonComponent(hex)` (e.g. same S, varying H/L); `contrastLightDark(hex)` (same H, min and max L). Register. |
| 7.5 | **Hue contrast** | `hueContrast(hex)` — base + one or two distant hues (e.g. +150°, +210°). Register. |
| 7.6 | **Ostwald grey** | `ostwaldGrey(hex)` — 3 grays, e.g. 20%, 50%, 80% lightness. Register. |
| 7.7 | **Warm / cool / earth** | `warmPalette(hex)` (hues in 0–60°), `coolPalette(hex)` (hues 180–300°), `earthTones(hex)` (desaturated warm). Register. |
| 7.8 | **Studio UI** | Color Palette Studio already uses `listHarmonies()`; once new types are in HARMONIES, they appear. Ensure dropdown or button list doesn’t overflow; consider grouping (e.g. “Basic”, “Advanced”, “Temperature”) in the UI if needed. |
| 7.9 | **Metadata** | For each new type, set `name`, `description`, `bestFor` in HARMONIES so the studio can show them. |

**Deliverable:** Color Harmony Engine has all fundamental + advanced + selected historical/temperature types; Color Palette Studio offers them; no broken references (square, achromatic, polychromatic, diad implemented).

---

## 8. Suggested Implementation Order

| Phase | Items | Rationale |
|-------|--------|-----------|
| **1** | Fix harmony engine (7.1), then add remaining harmony types (7.2–7.9) | Unblocks Studio; no layout dependency. |
| **2** | Toggle/button color coding (Section 6): admin CSS, Site Settings toggles, audit | Quick win; improves Site Settings and Feature Control parity. |
| **3** | Back buttons audit and fill gaps (Section 3) | Independent; improves navigation. |
| **4** | Sidebar audit and any missing collapse (Section 2) | Confirm one collapsible pattern everywhere. |
| **5** | Site Settings tabs or accordions (Section 4) | Makes long form manageable; enables co-locating theme (Section 5). |
| **6** | Theme & color co-location and preview doc (Section 5) | Finishes consolidation once tabs exist. |
| **7** | Optional: full-page preview (Section 5.4), summary fieldset (Section 4.5) | If time and priority allow. |

---

## 9. Preview System – Current State (Reference)

- **Small-screen preview:** `theme_preview_section.html` — mini sidebar + cards; updates when colors change; contrast check.
- **Toggle preview mode:** Session-based “sandbox” so staged changes can be viewed on real pages before saving.
- **Customizer:** `siteconfig:customizer` — separate page for theme pack selection; links to Site Settings.
- **Full-page iframe in change form:** Not implemented; can be added as optional (Section 5.4).

---

## 10. Files to Touch (Summary)

| Area | Files |
|------|--------|
| **Sidebar** | `templates/partials/portal_sidebar.html`, `templates/portal_base.html`, `templates/backend_base.html` (if different), CSS for collapse (portal-layout-professional.css or inline). |
| **Back buttons** | Templates that have or need back links (see Section 3 audit); `static/css/design-system-unified.css` (already has .btn-back-*). |
| **Site Settings** | `templates/admin/siteconfig/sitesettings/change_form.html` (tabs/accordions), optionally `apps/siteconfig/admin.py` (fieldsets grouping). |
| **Color / preview** | Same change_form; `templates/admin/components/color_palette_studio.html`, `theme_preview_section.html`; `static/js/color-palette-studio.js`. |
| **Toggles/buttons** | `apps/siteconfig/forms.py` (SiteSettingsForm toggle classes), `templates/admin/siteconfig/sitesettings/change_form.html` (CSS), `templates/admin/base_site.html` (toggle-colors.css), `static/css/toggle-colors.css`. |
| **Harmony** | `static/js/color-harmony-engine.js` (implement square, achromatic, polychromatic, diad + new types); `static/js/color-palette-studio.js` (if grouping harmony list in UI). |

---

## Next Step

- **Decide which phase to do first** (e.g. Phase 1 harmony + Phase 2 toggles).
- **For Site Settings:** Choose tabs vs accordions and whether to add a summary fieldset.
- **For sidebars:** Confirm which base templates render a sidebar and that they all use the same collapsible pattern.

Once you confirm priorities, we can break the chosen phase into concrete tasks and implement step by step.
