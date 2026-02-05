# Theme & Color Fix – Step-by-Step Implementation Plan

This plan implements the gaps from `THEME_AND_COLOR_GAPS_DETAILED_AUDIT.md` in a safe order: unify tokens first, then remove overrides, then clean templates.

---

## Phase A: Single Source of Truth (Tokens & Aliases)

**Goal:** One canonical primary and focus ring; everything else references it. No visual changes yet.

### Step 1 – Decide and document the canonical palette
- **Action:** Choose one “winning” primary for the whole app (recommended: Gilead pink from design-system-unified, i.e. `--color-primary` / `--color-primary-dark`).
- **Output:** One-line note in `docs/THEME_AND_COLOR_GAPS_DETAILED_AUDIT.md` or in a short `docs/THEME_CANONICAL_TOKENS.md`: “Canonical primary = `--color-primary` from design-system-unified; canonical focus = `--focus-ring-color` from design-tokens.”

### Step 2 – Alias design-tokens to canonical primary (optional)
- **File:** `static/css/design-tokens.css`
- **Action:** After the existing `--school-primary` / `--school-accent` lines, add aliases so existing uses keep working but follow the canonical palette, e.g.:
  - `--school-primary: var(--color-primary, #0d6efd);`
  - `--school-accent: var(--color-accent, #198754);`
  - (Only if design-system-unified loads before or with design-tokens in all bases; otherwise skip and do Step 3 first.)
- **Alternative:** If design-tokens loads first everywhere, instead set in design-system-unified: `--school-primary: var(--color-primary);` and `--school-accent: var(--color-accent);` so design-tokens can stay untouched and design-system-unified is the single source.

### Step 3 – Ensure focus ring token is used everywhere
- **File:** `static/css/design-tokens.css`
- **Action:** Keep `--focus-ring-color` and `--focus-ring-offset`. Add a dark-theme block (e.g. `html[data-bs-theme="dark"]`) that sets `--focus-ring-color: #60a5fa` (or `var(--color-info)`) so one token works in both themes.
- **Files:** `static/css/design-system-unified.css`, `static/css/phase7-design-system.css` (if kept)
- **Action:** Change `:focus-visible` to use `var(--focus-ring-color)` and `var(--focus-ring-offset, 2px)` instead of `var(--color-primary)` / `var(--primary)`.

### Step 4 – Alias phase7 primary to design-system (or remove phase7)
- **Option A – Keep phase7:** In `static/css/phase7-design-system.css`, at the top of `:root`, set `--primary: var(--color-primary);` and `--primary-dark: var(--color-primary-dark);` (and remove the hardcoded `#007bff` / `#0d6efd`). Ensure phase7 loads after design-system-unified where it’s used.
- **Option B – Retire phase7:** Find every template that loads phase7-design-system.css; switch to design-system-unified (or remove the link). Then delete or archive phase7-design-system.css.
- **Recommendation:** Prefer Option A first (low risk); Option B only if phase7 is redundant everywhere.

---

## Phase B: Focus Ring Unification

**Goal:** One focus style globally; special cases (e.g. topbar, sidebar toggle) use variables.

### Step 5 – Remove duplicate global focus rules in portal-theme-modes
- **File:** `static/css/portal-theme-modes.css`
- **Action:** Remove or comment out the global `:focus-visible` and `html[data-bs-theme="dark"] :focus-visible` blocks (lines ~33–39) so design-system-unified (or design-tokens + Step 3) wins. Keep the topbar-specific rules (`#themeToggle:focus-visible`, `.topbar-controls .btn-link:focus-visible`, `.topbar-controls .btn:focus-visible`) as-is (white outline on gradient).

### Step 6 – Admin sidebar toggle: theme-aware focus
- **File:** `static/css/admin_sidebar_enhanced.css`
- **Action:** Replace the hardcoded `outline: 2px solid #fff` on `.sidebar-collapse-toggle:focus-visible` with a variable, e.g. `var(--admin-sidebar-focus-ring, #fff)`. In the same file (or in admin theme overrides), set `--admin-sidebar-focus-ring` to `#fff` for dark sidebar and to a dark color (e.g. `#0f172a`) for light sidebar so the ring is always visible.

---

## Phase C: Button & Control Unification

**Goal:** Portal and backend buttons use the same primary tokens; no indigo/sunset split.

### Step 7 – Portal buttons use canonical primary
- **File:** `static/css/portal_theme.css`
- **Action:** For `.btn-primary` and `.btn-outline-primary:hover`, replace the sunset gradient with `var(--color-primary)` (and optionally `linear-gradient(135deg, var(--color-primary), var(--color-secondary))` if you want to keep a gradient). For `.btn-outline-primary`, set `color: var(--color-primary); border-color: var(--color-primary);` and use a theme-aware background (e.g. `var(--color-bg-primary)` or `transparent`). Remove hardcoded `#f7f9fc` and `rgba(160,75,254,0.35)`.

### Step 8 – Portal dark: outline primary and nav-pill/dropdown use primary
- **File:** `static/css/portal-theme-modes.css`
- **Action:** Replace `html[data-bs-theme="dark"] .btn-outline-primary` (and `:hover`) indigo (`rgba(102,126,234,...)`, `#a5b4fc`, `#c7d2fe`) with `var(--color-primary)` / `var(--color-primary-light)` (and matching alpha or `var(--color-primary-light)` for hover bg). Replace `--portal-nav-pill-bg-hover` and `--portal-nav-pill-bg-active` to use primary-based values (e.g. `rgba` of primary or `var(--color-primary-light)`). Replace `.dropdown-item:hover`/`:focus` background with the same primary-based token.

---

## Phase D: Muted Text & Contrast

**Goal:** One muted token per context; backend dark uses one shade; WCAG-safe.

### Step 9 – Backend dark: single muted token
- **File:** `static/css/backend-dark-theme.css`
- **Action:** At the top of the backend-dark block, define `--backend-text-muted: #94a3b8` (or `#b8c4d0` if you prefer slightly brighter). Replace every use of `#b8c4d0`, `#cbd5e1`, and `#94a3b8` for secondary/muted text in that file with `var(--backend-text-muted)`.

### Step 10 – portal_theme.css: tables and labels use tokens
- **File:** `static/css/portal_theme.css`
- **Action:** Replace `table thead th { background: #f8fafc }` with `background: var(--color-bg-light)` (or a portal-specific var). Add in `portal-theme-modes.css` a dark rule for `html[data-bs-theme="dark"] table thead th { background: var(--color-bg-light); }` (dark theme already sets that var). Replace `.kpi-pill .kpi-label` and `.insight-pill-row` / `.insight-note` / `.insight-footnote` and `.subject-list li` colors with `var(--color-text-muted)` or `var(--portal-text-muted)`.

---

## Phase E: Template Cleanup (Inline Styles → CSS / Vars)

**Goal:** No hardcoded hex/rgba in templates for colors that should be theme-driven; use classes or CSS variables.

### Step 11 – Shared components (highest reuse)
- **Files:** `templates/components/weather_widget.html`, `templates/components/user_dropdown.html`, `templates/components/recent_activity.html`, `templates/components/logo_watermark.html`, `templates/components/logo_admin_settings.html`, `templates/components/dashboard_header.html`, `templates/components/student_360_tabs.html`
- **Action:** Replace inline `style="... color: #...; background: ..."` with CSS classes (e.g. `.weather-widget-card`, `.avatar-placeholder`, `.card-header-gradient`, `.info-value--success`, `.info-value--primary`) defined in a single CSS file (e.g. `static/css/design-system-unified.css` or `components.css`) using `var(--color-primary)`, `var(--color-accent)`, `var(--color-text-primary)`, etc. Remove or minimize inline color/background.

### Step 12 – Admin dashboard and theme preset
- **Files:** `templates/admin/admin_dashboard.html`, `templates/admin/components/admin_theme_preset.html`
- **Action:** Move stat colors (Admins/Students/Teachers, Connection, Status, security alerts, etc.) to classes like `.stat-admins`, `.stat-students`, `.stat-success`, `.stat-danger` with colors from vars. Replace preset panel border/background `#ddd`, `#fafafa`, `#666` with vars or classes. Replace “End Session” and gradient avatars with classes.

### Step 13 – Portal and backend bases + sidebars
- **Files:** `templates/portal_base.html` (search/topbar), `templates/backend_base.html`, `templates/partials/portal_sidebar.html`
- **Action:** Replace inline rgba/hex for topbar search and sidebar activity items with CSS classes or variables (e.g. `--topbar-input-bg`, `--sidebar-activity-accent`).

### Step 14 – Dashboards and workflow pages
- **Files:** `templates/teacher/dashboard.html`, `templates/parent/dashboard.html`, `templates/accounts/profile.html`, `templates/accounts/workflow_center.html`, `templates/teacher/workflow_center.html`, `templates/parent/workflow_center.html`, `templates/finance/dashboard.html`, `templates/home.html`
- **Action:** Replace donut `--accent` hex with vars (`var(--color-success)`, `var(--color-secondary)`). Replace card borders/backgrounds and workflow borders with classes or `var(--portal-border)` / `var(--color-border)`.

### Step 15 – Reports, emails, and remaining templates
- **Files:** `templates/reports/term_report_cameroon.html`, `templates/reports/annual_report_cameroon.html`, `templates/emails/report_ready_en.html`, `templates/emails/base_branded.html`, `templates/widgets/finance_dashboard_widgets.html`, `templates/portal/kb_home.html`, `templates/siteconfig/feature_control_panel.html`, `templates/admin/portal/partials/syllabus_student_preview.html`
- **Action:** Replace muted colors (`#555`, `#666`) with a muted utility class or var. Ensure email primary uses the same default as canonical (e.g. `primary_color|default:'#0d6efd'` only if that’s the chosen fallback; otherwise align to `--color-primary` hex). Replace remaining inline gradients/borders with vars or classes.

---

## Phase F: Load Order & Documentation

**Goal:** Document and enforce who sets palette and focus; avoid accidental overrides.

### Step 16 – Document CSS load order and ownership
- **File:** `docs/THEME_AND_COLOR_GAPS_DETAILED_AUDIT.md` (Section 8) or a new `docs/CSS_LOAD_ORDER.md`
- **Action:** Write a short “Ownership” table: e.g. “Palette: design-system-unified. Focus ring: design-tokens (and design-system-unified uses its vars). Buttons: design-system-unified + admin-components; portal_theme and portal-theme-modes only override for layout/specifics and must use same vars.” List base templates and the order of stylesheets. Add a note: “Do not add new global overrides of `:focus-visible` or `--color-primary` unless in a theme-specific scope.”

### Step 17 – Final pass: remove or narrow overrides
- **Action:** Grep for `:focus-visible` and `--color-primary` / `--primary` and `.btn-primary` across CSS. Ensure no file that loads after design-system-unified (or design-tokens) redefines the canonical tokens globally without a clear scope (e.g. admin sidebar, topbar). If any redundant override remains, remove it or limit it to a specific class/context.

---

## Order Summary (Dependencies)

| Step | Depends on | Phase |
|------|------------|--------|
| 1    | –          | A     |
| 2    | 1          | A     |
| 3    | 1          | A     |
| 4    | 1, 2       | A     |
| 5    | 3          | B     |
| 6    | 3          | B     |
| 7    | 2 or 4     | C     |
| 8    | 7          | C     |
| 9    | –          | D     |
| 10   | –          | D     |
| 11–15| A–D done   | E     |
| 16–17| All        | F     |

**Suggested execution:** Do Phase A (Steps 1–4) first so all later steps build on one palette and one focus token. Then B (5–6), then C (7–8), then D (9–10). Template cleanup (E) can be done in parallel by file after C and D. Finish with F (16–17).

---

## Quick Reference: Files to Touch by Phase

- **Phase A:** `design-tokens.css`, `design-system-unified.css`, `phase7-design-system.css` (and optional `THEME_CANONICAL_TOKENS.md`).
- **Phase B:** `portal-theme-modes.css`, `admin_sidebar_enhanced.css`.
- **Phase C:** `portal_theme.css`, `portal-theme-modes.css`.
- **Phase D:** `backend-dark-theme.css`, `portal_theme.css`, `portal-theme-modes.css`.
- **Phase E:** Multiple templates (see Steps 11–15); one shared CSS file for new classes.
- **Phase F:** Audit doc and a final grep/cleanup.

This is the step plan; each step can be implemented and tested (e.g. visual check in admin, portal, backend, light/dark) before moving to the next.
