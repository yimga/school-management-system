# Admin Forms & Child Menus – Theme and Styling Plan

## Goal

Change the **styling, display, theme, and background** of all admin **sidebar child menus and forms** (e.g. People Management → Student profiles) so they feel consistent, readable, and welcoming—moving away from the current heavy dark navy look while keeping a single, cohesive admin experience.

---

## Current State

- **Main content area** (`#content`, `#content-main`): In **dark mode**, background is set to **dark navy** (`#0f172a`) via `--admin-content-bg` in:
  - `static/css/admin-dark-readability.css`
  - `static/css/admin-content-readability.css` (dark overrides)
- **Form sections** (Identity, Profile, Guardians & contact, etc.): Use `.module`, `.aligned .form-row`; backgrounds and borders come from `admin_theme.css` and design tokens (`--color-bg-primary`, `--color-border`), which in dark theme are also dark.
- **Inputs**: White/light backgrounds in the screenshot are from Unfold or overrides; labels and section headings are light text on dark.
- **Result**: Entire form page (breadcrumbs, headings, fieldsets, inputs, buttons) sits on a dark blue/navy canvas. You want this updated for better visual appeal and clarity.

---

## Design Principles (from your guide, adapted for admin)

The children’s menu guidance emphasizes **high contrast**, **clear typography**, **bright/clear colors**, and **clear structure**. For admin forms we use the same ideas in a professional way:

| Principle | For admin forms & child pages |
|-----------|-------------------------------|
| **Visual appeal & theme** | One clear theme (light or dark) with a consistent palette; avoid “muddy” navy; use a recognizable accent for actions and links. |
| **Font & readability** | Keep sans-serif; ensure labels, headings, and body text have strong contrast (WCAG AA); comfortable size and spacing. |
| **Structure & content** | Group fields into clear sections (Identity, Profile, Guardians…) with visible section headers and dividers; short labels; consistent spacing. |
| **High contrast** | Background vs text and inputs vs labels must meet contrast requirements in both light and dark. |
| **Interactive elements** | Buttons, links, and focus states use a consistent accent; “Remove”/danger stays distinct; primary actions are obvious. |

No literal “playful” or kids’ visuals—just a **clear, structured, easy-to-scan** form and list experience.

---

## Scope

- **Sidebar child menus**: Any admin list or form reached via the sidebar (e.g. People Management → Student profiles, Teacher profiles, etc.).
- **In scope**: `#content` / `#content-main` background and surface colors, `.module` / section styling, `.form-row`, labels, inputs, select, textarea, `.submit-row`, breadcrumbs, changelist tables (list views).
- **Out of scope**: Sidebar itself (already configurable via Site settings); dashboard layout; Unfold structural markup (we only override styles).

---

## Phased Plan

### Phase 1: Content area tokens and background

**Objective:** Control main content background and text via a single set of variables so we can offer a “lighter” or “softer” option for forms without breaking the rest of the admin.

1. **Define admin-content theme variables** (light and dark) in one place, e.g.:
   - **Light:** `--admin-content-bg`, `--admin-content-surface`, `--admin-content-text`, `--admin-content-text-muted`, `--admin-content-border`, `--admin-content-accent`.
   - **Dark:** Same names, with values that either keep a **refined dark** (e.g. softer slate `#1e293b` instead of `#0f172a`) or switch to a **light form** (e.g. light grey/white form surface on a neutral dark frame).
2. **Use these variables** in:
   - `admin-content-readability.css` for `#content`, `#content-main`, headings, breadcrumbs, tables.
   - `admin-dark-readability.css` so dark theme only overrides with the chosen dark (or light-form) palette.
3. **Optional:** Add a Site setting (e.g. “Use light background for admin forms in dark mode”) and inject a class or data attribute so CSS can switch form background independently of the sidebar.

**Deliverable:** Main content and form canvas use design tokens; dark mode no longer forces heavy navy by default (or we introduce a “soft dark” / “light forms” option).

---

### Phase 2: Form sections and modules

**Objective:** Sections like “Identity”, “Profile”, “Guardians & contact” are visually distinct and easy to scan.

1. **Section containers** (`.module` used as fieldset wrapper, `.aligned .form-row`):
   - Use `--admin-content-surface` (or card-style token) for section background.
   - Clear border using `--admin-content-border`, rounded corners, subtle shadow.
   - Consistent padding and margin between sections.
2. **Section headings** (`.module h2`, `.module caption`):
   - Sans-serif, font-weight 600–700, size and color from `--admin-content-text` (or heading token).
   - Optional: small accent bar or left border in `--admin-content-accent` for consistency with sidebar/dashboard.
3. **Ensure** all form pages (Django admin change_form, inline formsets) use these classes so the look is consistent across apps (People, Academics, Finance, etc.).

**Deliverable:** Every form section has a clear card/surface, heading, and spacing; no “flat” dark block.

---

### Phase 3: Inputs, labels, and focus

**Objective:** Inputs and labels are high-contrast and accessible; focus and hover are obvious.

1. **Labels** (`#content label`, `.aligned label`, `.form-row label`):
   - Color from `--admin-content-text`; ensure contrast on the chosen background.
   - Sans-serif, consistent size (e.g. 14px base); required asterisk in a consistent danger color.
2. **Inputs** (text, number, date, select, textarea, file):
   - Background: either same as content surface or a dedicated “input surface” (e.g. white on light theme, light grey on dark) so they’re not “white holes” on dark.
   - Border: `--admin-content-border`; focus: `--admin-content-accent` or `--focus-ring-color` with visible outline/ring.
   - Placeholder and helper text use `--admin-content-text-muted`.
3. **Remove hardcoded colors** in admin form CSS (e.g. `rgba(255, 106, 136, 0.1)` for focus); use tokens so theme changes don’t require editing many files.

**Deliverable:** All form fields and labels use tokens; focus and hover states are consistent and WCAG-friendly.

---

### Phase 4: Buttons, submit row, and links

**Objective:** Primary/secondary/danger actions are clear and aligned with the rest of the admin theme.

1. **Submit row** (`.submit-row`):
   - Background and border from content tokens; primary button uses `--admin-content-accent` (or design-system primary).
   - Spacing and alignment already improved; ensure dark mode uses the same tokens.
2. **Links** (breadcrumbs, “Add another”, “Remove”):
   - Breadcrumbs: accent color; current page muted.
   - “Add another” / “Remove”: keep existing semantics (e.g. accent for add, danger for remove); ensure they use tokens.
3. **Inline and list actions**: Same accent/danger tokens so they match the dashboard and sidebar theme.

**Deliverable:** Buttons and links on form and list pages use the same token set; no stray hardcoded hex for primary/danger.

---

### Phase 5: List views (changelist) and consistency pass

**Objective:** List views (e.g. list of students) match the same theme as forms; one cohesive “child menu” experience.

1. **Changelist** (`.results`, `#result_list`, `.module table`):
   - Table background, header, and row colors from `--admin-content-*` tokens.
   - Striped/hover rows and borders consistent with form sections.
2. **Filters** (`#changelist-filter`): Same surface and border tokens as form sections.
3. **Audit** other admin pages reached from the sidebar (e.g. custom views, reports) and apply the same tokens where they render inside `#content`.

**Deliverable:** Every sidebar child view (form or list) uses the same content theme; no leftover dark navy unless explicitly chosen.

---

## Files to touch (summary)

| File | Role |
|------|------|
| `static/css/admin-content-readability.css` | Main `#content` and toolbar; light defaults; use tokens. |
| `static/css/admin-dark-readability.css` | Dark overrides; replace hardcoded `#0f172a` with tokens; optional “light form” or “soft dark”. |
| `static/css/admin_theme.css` | `.module`, `.form-row`, inputs, labels, submit row; switch to content tokens. |
| `static/css/admin-polish.css` | Any remaining `#content` / form background overrides; align with tokens. |
| `static/css/design-tokens.css` (optional) | Add `--admin-content-*` defaults if we want a single source of truth. |
| Site config / base_site (optional) | If we add “Light form background in dark mode” or “Admin content theme” option. |

---

## Optional: “Light form” or “Refined dark” default

- **Option A – Refined dark:** Keep dark mode but use a softer content background (e.g. `#1e293b` or `#334155`) and slightly lighter borders/text so it’s less “heavy navy” while still dark.
- **Option B – Light forms in dark mode:** In dark mode, keep sidebar dark but set `#content` (and form modules) to a light surface (e.g. light grey/white) so forms always look like your screenshot’s inputs (light fields) with dark only for sidebar and header. Easiest to implement with a single variable swap in dark theme.
- **Option C – Respect theme toggle only:** No separate “form theme”; light/dark follows the existing theme toggle everywhere (content + sidebar). We only soften the dark palette (Option A) so it’s less navy.

Recommendation: Start with **Option A** (refined dark) so we don’t introduce a second “form theme” toggle; if you prefer light forms in dark mode, we add Option B in Phase 1.

---

## Success criteria

- [x] No default heavy navy (`#0f172a`) for main content unless user explicitly chooses a “dark navy” preset. **(Done: refined dark `#1e293b` / `#334155`.)**
- [x] All form sections (Identity, Profile, Guardians, etc.) have clear structure: surface, heading, spacing, optional accent.
- [x] Labels and inputs use high-contrast, token-driven colors; focus states are visible and consistent.
- [x] Submit row, breadcrumbs, and links use the same accent/danger tokens as the rest of the admin.
- [x] List views (changelist) and filters use the same content theme as forms.
- [x] One place (or a small set of tokens) controls content background and surfaces for both light and dark.

---

## References

- Existing theme docs: `docs/ADMIN_UI.md`, `docs/THEME_SYSTEM.md`, `docs/ADMIN_SIDEBAR_RESTRUCTURE_PLAN.md`.
- Design principles above are adapted from your children’s menu guidance (high contrast, sans-serif, clear structure, bright/clear colors) for a professional admin UI.
