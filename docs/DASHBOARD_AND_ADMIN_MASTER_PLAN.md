# Dashboard & Admin Master Plan

A single, detailed plan that merges:
1. **Dashboard Clean & Classy** (whitespace, cards, typography, sidebar polish, charts, buttons, color restraint).
2. **Your new requirements**: collapsible sidebars for all users, back buttons (color-coded), Site Settings improvements, Color Palette Studio + Color Picker + ThemePacks consolidation with side-by-side layout and real-time preview, button/toggle color coding site-wide (including Site Settings, inspired by Feature Control), and expanded Color Harmony types.

---

# Part A: Dashboard Clean & Classy (Existing Plan Summary)

*(Full detail remains in `DASHBOARD_CLEAN_CLASSY_PLAN.md`.)*

| Phase | Focus | Deliverable |
|-------|--------|-------------|
| A1 | Tokens & base | Dashboard tokens (radius, spacing, shadow, type scale) |
| A2 | Card system | One card style: 12px radius, one shadow or border, 16px padding |
| A3 | Spacing & layout | 16–24px gutters; optional compact mode |
| A4 | Typography hierarchy | Page → section → card → body → caption |
| A5 | Sidebar polish | Clear active state, comfortable padding |
| A6 | Charts & data viz | Subtle grid, 2–3 colors, clear labels |
| A7 | Buttons & controls | Consistent height, radius, primary/outline |
| A8 | Color restraint | Neutrals + primary + semantic only |
| A9 | Content & copy | Shorter labels, one idea per card |
| A10 | Responsive & QA | All dashboards checked |

**Suggested order:** A1 → A2 → A3 → A4 → A8 → A5 → A6 → A7 → A9 → A10.

---

# Part B: New Requirements – Evaluation & Detailed Plan

## B1. Collapsible Sidebars for All Users (Like /admin)

### Current state
- **Admin (`/admin`):** Sidebar is collapsible. `#nav-sidebar.sidebar-collapsed` hides text, shows icons; `sidebar-collapse-toggle` toggles; state can be stored (e.g. `default_sidebar_collapsed`, dashboard prefs).
- **Portal/Backend (`/backend`, `/parent`, `/teacher`):** Portal sidebar (`partials/portal_sidebar.html`) is **not** collapsible. It’s a fixed-width column; on mobile it’s an offcanvas. No collapse toggle or icon-only mode.

### Goal
- Every user-facing sidebar (portal sidebar used on backend, parent, teacher) can be collapsed to an icon-only strip, with a persistent toggle and optional user preference.

### Plan

| Step | Action | Files / notes |
|------|--------|----------------|
| B1.1 | Add collapse toggle to portal sidebar | `partials/portal_sidebar.html`: add a button (e.g. chevron left/right) that toggles a class on the sidebar wrapper (e.g. `portal-sidebar-collapsed`). |
| B1.2 | Add CSS for collapsed state | New or existing CSS (e.g. `portal-layout-professional.css` or `portal-theme-modes.css`): when `portal-sidebar-collapsed`, narrow sidebar width (e.g. 60–64px), hide nav text (keep icons), show tooltips on hover (like admin). Reuse patterns from `admin_sidebar_enhanced.css` (opacity: 0 on text, overflow: hidden, center icons). |
| B1.3 | Persist preference | Use existing dashboard/preference mechanism if available (e.g. `DashboardUserPreference.sidebar_collapsed` or similar); otherwise localStorage. Toggle reads/writes preference and applies class on load. |
| B1.4 | Adjust main content width | When sidebar is collapsed, main content area grows (e.g. `portal-main-col` flex or width calc). Ensure resize handle (if any) still works or is hidden when collapsed. |
| B1.5 | Mobile | On small screens, keep current offcanvas behavior; collapse toggle can be hidden or only affect desktop. |

**Deliverable:** Portal sidebar (backend/parent/teacher) collapsible like /admin, with toggle and optional saved preference.

---

## B2. Back Buttons in Appropriate Locations (Color-Coded)

### Current state
- Back links exist in many places (e.g. “Back to dashboard”, “Back to list”, “Back to Feature Control”) but are inconsistent: mix of `btn-outline-secondary`, `btn-outline-primary`, `btn-link`, and inline styles. Not all detail pages have a back button in a consistent position.

### Goal
- Every “detail” or “child” page has a clear back button in an appropriate location (e.g. top-left of content or below page title).
- Back buttons are **color-coded by intent**: e.g. primary (back to main app), secondary (back to list), or contextual (e.g. warning for “discard and go back”).

### Plan

| Step | Action | Files / notes |
|------|--------|----------------|
| B2.1 | Define back-button semantics and CSS classes | Introduce or standardize: `.btn-back-primary`, `.btn-back-secondary`, `.btn-back-outline`. Map to existing Bootstrap + design tokens (e.g. primary = blue, secondary = gray). Document in a short “UI patterns” note. |
| B2.2 | Audit all templates for “back” links | From grep: ~30+ templates have back links. List each: template, current text, current class, target URL. |
| B2.3 | Standardize placement | Prefer: one back button at the top of main content (e.g. first element inside `{% block content %}` or after breadcrumbs). Pattern: `<a href="..." class="btn btn-sm btn-back-primary"><i class="bi bi-arrow-left"></i> Back to X</a>`. |
| B2.4 | Apply color coding | Back to **dashboard/home** → primary. Back to **list/parent section** → secondary. Back to **admin/config** → outline or secondary. Use the new classes so we can change globally later. |
| B2.5 | Add back button where missing | Identify pages that are “detail” or “child” (e.g. certification session detail, document edit, invoice detail) and add a back button with the right target and class. |

**Deliverable:** Consistent, color-coded back buttons across the app; no page that should have a back button lacks one.

---

## B3. Site Settings Page Improvements (Easier Administration)

### Current state
- Site Settings is one very long Django admin change form with **many fieldsets** (Branding, Preview & Draft, Company Details, Login/Header/Layout, Theme & Experience, Admin Portal, Portal Content, Footer, System Behavior, Feature Toggles, Backend Orchestration, Notifications, Compliance, Analytics Defaults, Metadata).
- Color Palette Studio, Admin Dashboard Palette Selector, Admin Theme Preset, and Theme Preview Section are included **below** the form (`after_field_sets`), so they appear after all fields. No side-by-side layout; admin must scroll to see theme/color tools and preview together.

### Goal
- Make the Site Settings page easier to use: clearer structure, less scrolling, and (where possible) grouping of related items with Color/Palette/Theme and a preview visible together (see B4).

### Plan

| Step | Action | Files / notes |
|------|--------|----------------|
| B3.1 | Group fieldsets into tabs or accordions | Keep one change form but group fieldsets into high-level sections (e.g. “Branding & theme”, “Company & login”, “Portal & features”, “Backend & compliance”, “Analytics & metadata”). Use Django admin’s existing mechanisms or a custom template: tabs (e.g. Bootstrap nav-tabs) or collapsible accordions so the page is scannable. |
| B3.2 | Move “Theme & Experience” + color tools into a prominent block | In the Site Settings change form template, add a distinct section (or tab) that contains: Theme & Experience fieldset **and** Color Palette Studio + Color Picker (and optionally ThemePack selector) **and** preview (see B4). So admin sees “change theme/colors” and “see result” in one place. |
| B3.3 | Reduce perceived length | Optional: “Summary” fieldset at top with only site name, logo, primary color, and link “Edit full settings below”. Rest of fieldsets in tabs/accordions. |
| B3.4 | Sticky “Save” and “Preview” | Keep Save (and optionally “Clear preview”) visible (e.g. sticky bar or floating button) so admin doesn’t have to scroll to bottom on long form. |

**Deliverable:** Site Settings page is easier to navigate (tabs/accordions), with theme/color and preview co-located (after B4).

---

## B4. Consolidate Color Palette Studio, Color Picker, and ThemePacks + Side-by-Side + Preview

### Current state
- **Color Palette Studio:** Reusable component (base color swatch, harmony types, generated palette, apply to form). Used in: Site Settings change form, ReportCardStyle change form, ThemePack change form.
- **Color Picker:** Individual fields (e.g. `primary_color`, `accent_color`) use `ColorInputWithPreview()` (likely Pickr or similar). They live inside the “Theme & Experience” fieldset.
- **ThemePacks:** Model and admin; selected via `theme_pack` / `admin_theme_pack` dropdown in Site Settings. `admin_dashboard_palette_selector.html` shows preset cards; applying one updates form fields.
- **Preview:** “Small screen preview” (`theme_preview_section.html`) shows a mini sidebar + cards and updates when colors change. There is also `toggle_preview_mode` (sandbox) for staging changes. No single “preview frame” that shows the actual site or admin in an iframe next to the form.

### Goal
- **Consolidate:** One coherent “Theme & color” experience: Color Palette Studio and Color Picker (for primary/accent/header/footer etc.) and Theme/ThemePack selector live together conceptually and in the UI.
- **Layout:** Color Palette Studio + Color Picker **side by side** with the “Theme and experience” section (and ThemePack selector), so the admin sees what they’re changing in one view.
- **Preview:** A visible “preview frame” (e.g. iframe or live mini view) that shows how the site/admin will look when changes are applied (real-time where feasible).
- **Clarify:** Whether “preview” means (a) the existing “Small screen preview” + contrast check, (b) a full-page iframe (e.g. portal or admin index), or (c) both. Document and implement accordingly.

### Plan

| Step | Action | Files / notes |
|------|--------|----------------|
| B4.1 | Define “Theme & color” layout on Site Settings | In `admin/siteconfig/sitesettings/change_form.html`, restructure so one row/section contains: [Left column] Theme & Experience fieldset (including theme_pack, backend_console_theme, primary_color, accent_color, etc.) + Color Palette Studio (collapsible or always visible). [Right column] Preview frame (see B4.2). Optionally: Admin Dashboard Palette Selector and Admin Theme Preset in the same block. |
| B4.2 | Add or reuse preview frame | **Option A:** Expand “Small screen preview” to a larger card and keep it in the right column; ensure it reacts to color/theme changes (already does via JS). **Option B:** Add an iframe that loads a preview URL (e.g. `/preview/` or admin index with preview mode) so the admin sees a real page. **Option C:** Both: small preview + optional “Open full preview in new tab”. Prefer Option A first for simplicity; add Option B if needed. |
| B4.3 | Wire Color Palette Studio to form fields in real time | Ensure when a palette is applied from the studio, the corresponding form fields (primary_color, accent_color, etc.) update and the preview (and any iframe) refresh. Already partially there; verify and document. |
| B4.4 | Single “Theme & experience” section | In admin, ensure there is one clear section title “Theme & experience” that contains: theme pack selector, color fields, Color Palette Studio, and preview. Remove duplication (e.g. color fields only once). |
| B4.5 | Document preview system | Add a short doc or comment: what “preview” exists (small screen preview, contrast check, toggle_preview_mode), where it lives, and how to add a full-page preview later if desired. |

**Deliverable:** Site Settings has a side-by-side “Theme & color” + preview block; Color Palette Studio and Color Picker are visually and functionally next to Theme/ThemePack; preview updates in real time.

### B4 Clarification: Consolidation = Layout & UX, Not Code Merge

| What | In the plan | Not in the plan (optional later) |
|------|-------------|-----------------------------------|
| **ThemePacks** | Stay a model; selector (dropdown + preset cards) moves into the same “Theme & experience” section as Studio and Picker. | Merging ThemePack into one “presets” UI inside the Studio (e.g. “Save as ThemePack” from Studio). |
| **Color Picker** | Stays the widget (`ColorInputWithPreview`) for `primary_color`, `accent_color`, etc.; those fields are shown in the same section as the Studio and ThemePack selector. | Replacing individual picker fields with a single “picker inside Studio” (would require form-field mapping). |
| **Color Palette Studio** | Same reusable component; included once in that section; “Apply to form” continues to fill the same Site Settings color fields. | Turning Studio into the only way to set colors (removing standalone picker fields). |

So: **one place** (one section, one layout) for ThemePacks + Color Studio + Color Picker + preview; **no removal** of ThemePack model, Color Picker widget, or Studio component.

### B4 Impact Summary

| Area | Impact |
|------|--------|
| **Site Settings** | One “Theme & experience” section (tabs/accordions per B3); left column: theme pack dropdown, color fields (picker), Color Palette Studio; right column: preview. Duplicate “Color Picker” headings (today in `admin_theme_preset.html` and `admin_dashboard_palette_selector.html`) can be unified into one “Theme & color” heading. |
| **ThemePack admin** | No change to ThemePack model or `ThemePackAdmin`; ThemePack change form still includes Color Palette Studio for editing that pack’s colors. Only Site Settings layout changes. |
| **ReportCardStyle admin** | No change; ReportCardStyle change form still includes Color Palette Studio. Same component, different form. |
| **Portal customizer** | `siteconfig:customizer` (theme pack selection page) unchanged; it links to Site Settings. Users still choose a pack there or in Site Settings. |
| **Backend/Admin theming** | No change to how `theme_pack` / `admin_theme_pack` are applied (context_processors, templates). Only where admins **edit** theme/colors (Site Settings) is reorganized. |
| **Preview** | Small screen preview (and optional iframe) lives in the new right column; JS that updates preview on color change stays; optional “Open full preview in new tab” can be added. |

If you later want **deeper merging** (e.g. “ThemePacks as presets inside the Studio”, or “one unified color tool”), that can be a separate phase after B4.

---

## B5. Button and Toggle Color Coding (Site-Wide, Including Site Settings)

### Current state
- **Feature Control panel:** Toggles use Bootstrap form-switch; **On** = green badge + checked state; **Off** = grey badge. Clear and color-coded.
- **toggle-colors.css:** Already defines `.form-switch .form-check-input:checked` → success green; `:not(:checked)` → muted grey (and dark mode). So **toggles** are already color-coded in one place.
- **Site Settings:** Many boolean/checkbox fields (e.g. `use_dark_mode`, `show_header_search`, `enable_parent_portal`). They use Django’s default or Bootstrap form-switch; they may not all pick up `toggle-colors.css` if loaded after admin CSS, or if admin uses different class names.
- **Buttons:** Primary/secondary/outline are not explicitly “color-coded” for “enabled vs disabled” or “applied vs not applied” beyond Bootstrap’s default. You want **buttons** (e.g. “Save”, “Apply”, “Enable”) to also be clearly coded (e.g. success for “on/applied”, muted for “off”).

### Goal
- **Toggles:** Every form-switch (Site Settings, Feature Control, and anywhere else) uses the same color coding: **ON = green (success), OFF = grey**, regardless of themepack. Feature Control remains the reference.
- **Buttons:** Action buttons that represent “enabled”, “applied”, or “active” are visually distinct (e.g. success or primary); “disabled” or “inactive” are muted. Standardize so it’s obvious across the platform.

### Plan

| Step | Action | Files / notes |
|------|--------|----------------|
| B5.1 | Ensure toggle-colors.css loads everywhere | Verify it’s included in admin base (`admin/base_site.html` or equivalent), portal_base, backend_base, and base.html. If not, add it so all form-switch inputs get the same rules. |
| B5.2 | Audit Site Settings form | List every checkbox/boolean on Site Settings. Ensure each uses `form-check form-switch` and `form-check-input` so they get the global toggle styling. Adjust Django admin form/widget or template if some use raw checkboxes. |
| B5.3 | Audit rest of codebase for toggles | Grep for `form-check-input`, `form-switch`, `type="checkbox"` in templates and forms. Ensure they use the same classes so toggle-colors.css applies. Add a single utility class if needed (e.g. `.toggle-colored`) for any edge cases. |
| B5.4 | Buttons: define semantic classes | Document (and implement in CSS): e.g. `.btn-state-on` / `.btn-state-off`, or use existing `.btn-success` / `.btn-secondary` consistently for “action applied” vs “action not applied”. Apply to key actions (e.g. “Save”, “Enable”, “Apply”) where state is visible. |
| B5.5 | Feature Control as reference | Keep Feature Control panel as the gold standard: green for On, grey for Off, badges next to each row. Reuse the same CSS variables (e.g. `--brand-success`) so themepack can change primary but success green stays recognizable for “on”. |

**Deliverable:** All toggles (including Site Settings) color-coded green/grey; buttons that represent state are consistent; Feature Control pattern applied site-wide.

---

## B6. Expand Color Harmony Types

### Current state (color-harmony-engine.js)
- **Present:** complement, splitComplementary, triadic, analogous, monochromatic, tetradic (6 types).
- **Missing (from your list):** Square (tetradic but 90° spacing), Achromatic (neutrals only), Polychromatic (5+ colors, same tint/tone/shade), Diad (two colors separated by one slot on the wheel).

### Goal
- Add the following harmony types so the Color Palette Studio and any color tools can use them:
  - **Square** (four colors, 90° apart).
  - **Achromatic** (black, white, grays; no hue).
  - **Polychromatic** (e.g. 5 colors, same lightness or same saturation).
  - **Diad** (two colors, e.g. base and base+60° or base+120° depending on definition).

Reference: Your list — Monochromatic, Analogous, Complementary, Split-Complementary, Triadic, Tetradic (double-complementary), Square, Achromatic, Polychromatic, Diad.

### Plan

| Step | Action | Files / notes |
|------|--------|----------------|
| B6.1 | Implement `square(hex)` | Four colors at 0°, 90°, 180°, 270° (same as tetradic in many definitions; if current tetradic is “rectangle” with two pairs, square = equal spacing). Add to color-harmony-engine.js and HARMONIES. |
| B6.2 | Implement `achromatic(hex)` | Ignore hue of input; produce array of grays (e.g. from black to white, or based on lightness of input). e.g. 3–5 grays: #111, #555, #999, #ccc, #f5f5f5. Add to HARMONIES. |
| B6.3 | Implement `polychromatic(hex)` | e.g. 5 colors: base + 72°, 144°, 216°, 288° (pentagon), or 6 colors (hexagon). Optionally adjust saturation/lightness to “tie” them (e.g. same L or same S). Add to HARMONIES. |
| B6.4 | Implement `diad(hex)` | Two colors: base and base + 60° (or one step on a 12-part wheel). Add to HARMONIES. |
| B6.5 | Register in Color Palette Studio | In color-palette-studio.js, add the new harmony keys to the list of buttons and to the `harmonyType` state so the UI can select them and call `colorHarmony.generate(harmonyType, baseHex)`. |
| B6.6 | Add metadata | For each new type, add `name`, `description`, `bestFor` in HARMONIES so the studio can show them. |

**Deliverable:** Color Harmony Engine supports 10 types (complement, splitComplementary, triadic, analogous, monochromatic, tetradic, square, achromatic, polychromatic, diad); Color Palette Studio offers all of them.

---

# Part C: Combined Implementation Order

Recommended order so that dependencies and “quick wins” are balanced:

| Order | Item | Why |
|-------|------|-----|
| 1 | **A1 Tokens** | Base for everything else. |
| 2 | **B5 Toggle & button color coding** | Fast, high impact; no layout change. Ensures Site Settings toggles and Feature Control pattern are consistent. |
| 3 | **B2 Back buttons** | Improves navigation quickly; independent of sidebar/preview. |
| 4 | **B6 Harmony types** | Purely additive; improves Color Palette Studio before we restructure Site Settings. |
| 5 | **A2 Cards + A3 Spacing** | Dashboard look and feel. |
| 6 | **B1 Collapsible portal sidebar** | Big UX win for backend/parent/teacher. |
| 7 | **B4 Color/Palette/Theme side-by-side + preview** | Depends on having a clear idea of layout (B3/B4). |
| 8 | **B3 Site Settings structure (tabs/accordions)** | Makes the long form manageable; can be done in parallel or after B4. |
| 9 | **A4 Typography, A5 Sidebar polish, A6 Charts, A7 Buttons, A8 Color** | Remaining dashboard polish. |
| 10 | **A9 Content, A10 QA** | Final pass. |

You can batch 1–4 first, then 5–6, then 7–8, then 9–10.

---

# Part D: Files to Touch (Summary)

| Area | Files |
|------|--------|
| **Collapsible sidebar** | `templates/partials/portal_sidebar.html`, `static/css/portal-*.css` or new, `portal_base.html` (main column width), context/prefs for state. |
| **Back buttons** | Many templates (see B2.2); one small CSS or pattern doc for `.btn-back-*`. |
| **Site Settings** | `templates/admin/siteconfig/sitesettings/change_form.html`, `apps/siteconfig/admin.py` (fieldsets), possibly custom JS for tabs/accordions. |
| **Color + preview** | `change_form.html`, `theme_preview_section.html`, `admin/components/color_palette_studio.html`, `static/js/color-palette-studio.js`, preview assets. |
| **Toggles/buttons** | `static/css/toggle-colors.css`, admin/base_site.html (include), Site Settings form widgets/template, any template with form-switch. |
| **Harmony** | `static/js/color-harmony-engine.js`, `static/js/color-palette-studio.js`. |
| **Dashboard clean** | As in `DASHBOARD_CLEAN_CLASSY_PLAN.md`: design-tokens.css, dashboard-high-contrast.css, dashboard-layout-unified.css, sidebar CSS, chart CSS, etc. |

---

# Part E: Preview System – Current State (Reference)

- **Small screen preview:** `theme_preview_section.html` – mini sidebar + cards; updates when colors change; contrast check.
- **Toggle preview mode:** `toggle_preview_mode` – session-based “sandbox” so staged changes can be viewed on real pages before saving.
- **Customizer:** `siteconfig:customizer` – separate page for theme pack selection and links to Site Settings.
- **No iframe “live site” preview** in the change form today; that can be added in B4.2 if desired.

---

# Part F: Additional Improvements to Consider Before Starting

Optional enhancements that will make the rollout smoother and the product more polished. Pick any to fold into the implementation order or do as a follow-up pass.

| Area | Suggestion | Notes |
|------|------------|--------|
| **Accessibility & focus** | Focus trap in modals; skip link “Skip to main content”; keyboard nav for sidebar (arrow keys, Enter to activate). | Helps screen-reader and keyboard-only users. |
| **Loading & empty states** | Skeleton loaders for dashboard cards/charts; clear empty states (“No referrals yet” + CTA) instead of blank areas. | Reduces perceived wait and clarifies next steps. |
| **Breadcrumbs** | One breadcrumb component; same placement (e.g. below header, above title) on admin, backend, portal. | Consistent wayfinding. |
| **Success/error feedback** | Toasts or inline alerts for “Saved”, “Applied”, “Error”; consistent placement (e.g. top-right or below header); optional auto-dismiss. | Users need clear confirmation. |
| **Search & filters** | Where lists/tables exist: consistent placement of search and filters; visible “Clear”/“Reset”; preserve filters in URL or state where useful. | Especially for backend/teacher/parent list views. |
| **Help & onboarding** | Short tooltips on key controls (e.g. Color Palette Studio, Feature toggles); “?” or “Help” link to docs; optional first-time hints for Site Settings. | Lowers support burden. |
| **Print & export** | Print styles for key pages (e.g. dashboards, reports); “Export” actions where data is exportable (CSV/PDF). | Already partially there; ensure new pages are covered. |
| **Performance** | Lazy-load heavy widgets (e.g. charts, Color Studio) where possible; defer non-critical CSS; keep preview iframe or Color Studio from blocking save. | Long Site Settings form and preview should stay responsive. |
| **Internationalization (i18n)** | All new UI strings in translatable blocks (`{% trans %}` / `gettext`); locale in design tokens if needed (e.g. RTL). | So new work is i18n-ready. |
| **Security / audit visibility** | Sensitive fields (e.g. API keys) masked in UI; audit log or “Recent changes” visible to admins where appropriate. | Align with compliance. |
| **Keyboard shortcuts** | Document and expose existing shortcuts (e.g. from `keyboard_shortcuts.html`); ensure new UI (sidebar collapse, Color Studio, modals) respects and advertises shortcuts. | Power users and accessibility. |
| **Dark mode parity** | Every new or touched component (collapsible sidebar, back buttons, Site Settings tabs, Color Studio) has dark-mode styles so theme switching is complete. | Avoids “half dark” experience. |
| **Graceful degradation** | If Color Studio or preview fails to load (JS error, ad blocker), show a fallback (e.g. “Theme preview unavailable – use form fields”) so the page still saves. | Prevents one component breaking the whole form. |
| **Theme undo / revert** | In Site Settings: “Revert to saved” or “Undo last change” for color/theme edits so admins can experiment safely. | Complements real-time preview. |

**How to use Part F:**  
- Before starting a batch, skim Part F and decide which items to include in that batch (e.g. “we’ll do focus management and empty states in batch 1–4”).  
- Or schedule a short “Part F pass” after Part C is done (e.g. accessibility + loading states + breadcrumbs in one pass).

---

# Next Step

- Decide which batch to implement first (e.g. 1–4: Tokens, Toggle/button color, Back buttons, Harmony types).
- Optionally choose 1–3 items from **Part F** to include in that batch.
- Then we can break that batch into concrete tasks and implement step by step.
