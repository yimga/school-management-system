# Theme visibility and contrast – entire codebase plan

This plan addresses white-on-white and low-contrast issues **across the whole codebase**, not only the Theme pack catalog. The goal is a **long-term, forward-thinking** approach: one guard layer, token-driven (no hardcoding), so text, cards, and badges stay readable in every theme and on every page, including future theme packs and new pages.

- **Unfold and codebase only:** All changes use Unfold and existing codebase patterns (no new theming systems or one-off selectors).
- **No hardcoding:** All colors, borders, and visibility values come from design tokens or the guard’s :root; raw hex/rgba only as canonical fallbacks in **one place** (design-tokens.css or guard :root). Every rule uses `var(--…)`.
- **All steps required:** Every item below (including data-dashboard-page for theme-colors, dashboard-text-visibility alignment, design-tokens, and docs) is part of the plan—no “optional” leftovers; everything is in scope for a complete, maintainable solution.

---

## No hardcoding (token- and config-driven only)

- **Colors and borders:** Use only CSS variables. Prefer `var(--vis-text-muted)`, `var(--color-base-600)`, `var(--admin-content-border)`, etc. If a value is not yet a token, add it once in `design-tokens.css` or in the guard’s `:root` / dark block (e.g. `--vis-text-muted`) and reference that variable everywhere else. No raw `#475569` or `rgba(15,23,42,0.12)` in multiple files.
- **Theme detection:** Use only existing attributes and classes the app already sets: `data-theme`, `data-bs-theme`, `portal-backend-light`, `portal-backend-dark`. No new body classes or data attributes for visibility; add path-based `data-dashboard-page` only via the existing portal_base script (see step 4).
- **Single source of truth:** Any value that might change (e.g. muted text color, card border) is defined in one place (tokens or guard :root). All guard and visibility rules use `var(--…)` with at most one fallback to another variable (e.g. `var(--vis-text-muted, var(--color-base-600))`). Hex/rgba only as the final fallback in that single definition. When adding new visibility rules in the future, introduce or reuse a token first; never add raw hex/rgba in the rule itself.

---

## Based on Unfold and codebase support

- **Unfold** is the Django admin theme (first in `INSTALLED_APPS`; `GileadAdminSite(UnfoldAdminSite)` in `config/admin.py`). Admin uses Unfold’s `ModelAdmin`, `#nav-sidebar`, and templates under `templates/unfold/helpers/`. Unfold is Tailwind-based and exposes:
  - **Tokens:** `--color-base-100` … `--color-base-900` (used in `admin-sidebar-*.css`, `base_site.html`, `color-palette-studio.css`, `toggle-colors.css`). The codebase uses these with fallbacks (e.g. `#e2e8f0`, `#0f172a`, `#64748b`).
  - **Classes:** `.text-subtle`, `.text-important` (e.g. in `unfold/helpers/site_icon.html`). `dashboard-text-visibility.css` already targets `.unfold .text-subtle` with `--admin-sidebar-text-muted`.
- **Theme detection (use only these):**
  - `html[data-theme]` and `html[data-bs-theme]` (set by portal_base/base; synced in `bootstrap-theme-bridge.css`).
  - `body.portal-backend-light` / `body.portal-backend-dark` (backend shell).
  - Unfold’s `.dark` in admin (see `admin_sidebar_enhanced.css`).
- **Design tokens the codebase uses:** `design-tokens.css` defines `--admin-content-*`, `--admin-sidebar-*`; `theme-visibility-guard.css` defines `--vis-*` (mapped from `--admin-surface`, `--admin-content-surface`, etc.). Use **only** these plus Unfold’s `--color-base-*` with fallbacks—no new variable names.
- **Load order:** Admin loads `design-tokens.css` → `design-system-unified.css` → … → `theme-visibility-guard.css` (base_site.html). Portal/backend load the guard from portal_base/base. So the guard runs after Unfold and design tokens; overrides should use the same selectors and light/dark branching as `dashboard-text-visibility.css` (`html[data-bs-theme="light"]`, `:root:not([data-theme="dark"])`, `body.portal-backend-light` / `portal-backend-dark`).

**Do not introduce:** New CSS variables Unfold doesn’t use; new body classes or data attributes that nothing sets; Tailwind-only classes the project doesn’t use elsewhere. Prefer mapping guard colors to Unfold-friendly fallbacks (e.g. `--vis-text-muted` fallback `#475569` aligns with `--color-base-600`).

---

## Scope (entire codebase)

- **Templates:** 80+ files use `text-muted`, `text-bg-light`, `bg-light`, or `bg-white` (accounts, teacher, parent, portal, admin, siteconfig, finance, evals, requests, analytics, etc.).
- **CSS:** Multiple stylesheets use `--color-text-primary`, `--color-surface`, `--admin-content-*`, `.card`, `.badge`, `.form-control`, `.help` (design-tokens, dashboard-*, backend-*, admin-*, portal-*, theme-visibility-guard, admin-color-preview, dashboard-text-visibility, etc.).
- **Entry points:** Guard must apply everywhere the app is used: portal (portal_base.html), backend (backend_base → portal_base), Django admin (base_site.html), and any base.html-only pages. theme-visibility-guard.css is already loaded from portal_base, base, and admin base_site, so extending it gives codebase-wide coverage.

---

## Pages that do not use the app shell

- **Current state:** Almost all app templates extend `portal_base.html`, `backend_base.html` (→ portal_base), `base.html`, or admin `base_site.html`. All of those load `theme-visibility-guard.css`, so the guard applies.
- **Exception:** **Admin login** (`templates/admin/login.html`) extends **Unfold’s** `unfold/layouts/unauthenticated.html`, not our base_site. So the admin login page does **not** load the guard. Auth login (`auth/login.html`), 404, and 500 extend `base.html`, so they get the guard.
- **Action:** If admin login should have the same visibility guarantees (no white-on-white, readable muted text), override `unfold/layouts/unauthenticated.html` in your project and add `theme-visibility-guard.css` in `{% block extrastyle %}` (or add the guard to the admin login template’s extrastyle). Otherwise document that admin login uses Unfold’s minimal layout and is out of scope for the guard.
- **New minimal pages:** Any future page that uses a layout that does **not** extend portal_base, base, or base_site should include the guard in that layout so visibility rules apply there too.

---

## Faded, blurred, or blocked text

- **Faded:** Several stylesheets set low **opacity** (e.g. `0.3`–`0.6`) on text or labels (e.g. `.modular-card .meta-tag` 0.6, empty-state icons 0.5, sidebar pin button 0.6, chart placeholders 0.5). That can make text look washed out or “blocked” visually.
- **Blurred:** `backdrop-filter: blur()` is used on some panels (teacher dashboard, admin components, theme preview). It blurs content *behind* the panel; text *on* the panel can still be readable, but if blur or overlay is applied to a container that has text inside, that text can look blurred.
- **Blocked:** Text can be “blocked” by (1) **overflow: hidden** + **text-overflow: ellipsis** (clipping), (2) an overlay or high z-index covering it, (3) **visibility: hidden** or very low opacity.
- **Guard approach:** In `theme-visibility-guard.css`, enforce a **minimum opacity for critical content** so body text, card content, form labels, and dashboard values are never faded: e.g. `.card-body`, `.card-body p`, `.card-title`, `.form-label`, `.help`, `.form-text`, `.dashboard-kpi-label`, `.dashboard-kpi-value` → `opacity: 1`. For secondary labels that are intentionally muted (e.g. `.meta-tag`), use a minimum of 0.9 so they stay readable. Do not remove blur from decorative panels; only ensure text that must be read is not inside a blurred container or has opacity 1.

---

## 1. Central guard: extend theme-visibility-guard.css (codebase-wide)

**File:** `static/css/theme-visibility-guard.css`

Keep existing `--vis-*` variables and Site Settings catalog block. Add the following so they apply **everywhere** this file is loaded (portal, backend, admin):

### 1a. Global text and helpers (Unfold + Bootstrap; no new tokens)

- **.text-muted and .small.text-muted**  
  Use the same light/dark branching the codebase already uses in `dashboard-text-visibility.css`. No hardcoded hex: light uses `color: var(--vis-text-muted) !important;` (guard :root sets `--vis-text-muted` from `--admin-content-text-muted` or `--color-base-600`; design-tokens holds canonical values). Dark uses existing dark `--vis-text-muted` block.
- **.help, .form-text**  
  Same as .text-muted so help text and form descriptions never disappear.
- **Unfold muted text:** Ensure `.unfold .text-subtle` stays readable (dashboard-text-visibility already sets it to `--admin-sidebar-text-muted`); in the guard, only add rules if needed so admin and portal use the same logic (e.g. guard applies in admin, so `.unfold .text-subtle` can use `var(--vis-text-muted)` when inside admin content area).

### 1b. Badges (app-wide; Bootstrap + Unfold-safe)

- **.badge.text-bg-light**  
  Use same theme detection as 1a. No hardcoded values: use only variables. On light: `border: 1px solid var(--vis-border)` (or `var(--color-base-200)`); `color: var(--vis-text)` (or `var(--color-base-800)`); `background: var(--vis-surface-muted)` (or `var(--color-base-100)`) so the badge is distinct. Dark: use existing dark `--vis-*` or `--color-base-*` tokens.

### 1c. Cards and surfaces (app-wide; Unfold/compatibility)

- **.card** (main content area):  
  No hardcoded border color: `border: 1px solid var(--vis-border);` (guard/design-tokens define `--vis-border`). Background stays inherited; guard only guarantees border.

### 1d. Theme pack catalog – Theme & Experience page

- Add a block that **mirrors** the existing “Site Settings / Theme pack catalog” rules but scoped to **.theme-experience-page** (the wrapper in `templates/siteconfig/theme_colors.html`).
- Reuse the same `--vis-*` variables for:
  - .theme-pack-catalog (and children: summary, .help, group title, filter row, badges, catalog body)
  - .admin-dashboard-palette-card (background, border, hover/selected)
  - .admin-dashboard-palette-name, .admin-dashboard-palette-desc, .theme-pack-catalog-hint, .form-check-label
- Add dark-theme variants for .theme-experience-page using existing dark `--vis-*` definitions.

Result: One file enforces readable text, badges, cards, and the catalog on every page that loads it (entire codebase that uses portal_base, base, or admin base_site).

---

## 2. admin-color-preview.css – global catalog fallbacks

**File:** `static/css/admin-color-preview.css`

- Keep existing Site Settings–only block unchanged.
- Add **global** rules (no body class) so the theme pack catalog is never white-on-white. No hardcoded colors: use only variables.
  - .theme-pack-catalog: background via `var(--vis-surface)` or color-mix with `var(--vis-surface)` and a dark token; border `1px solid var(--vis-border)`.
  - .admin-dashboard-palette-card: background `var(--vis-surface-muted)`; border `var(--vis-border)`.
  - .admin-dashboard-palette-name, .admin-dashboard-palette-desc: `color: var(--vis-text)` and `color: var(--vis-text-muted)` (canonical values live in guard :root / design-tokens).

---

## 3. dashboard-text-visibility.css – align with guard (Unfold already supported)

**File:** `static/css/dashboard-text-visibility.css`

- Already targets `.unfold .text-subtle` with `--admin-sidebar-text-muted` and uses theme selectors. **Required:** Replace any remaining hardcoded hex (e.g. #475569, #94a3b8) with variables: use `var(--admin-content-text-muted)` or `var(--vis-text-muted)` for muted text so the value is defined once in design-tokens or the guard. Keep this file as the Unfold-aware layer; guard and this file must share the same token references so one source of truth.

---

## 4. data-dashboard-page for Theme & Experience (in scope)

**File:** `templates/portal_base.html`

- **Required.** In the script that sets `data-dashboard-page`, add a branch for path containing `/siteconfig/theme-colors` (e.g. `page = "theme-colors"`) so `[data-dashboard-page]` is set and `[data-dashboard-page] .text-muted` and any dashboard-scoped rules apply on the Theme & Experience page. Use the same pattern as existing path checks (no hardcoded strings beyond the path fragment; use the same script structure as other pages).

---

## 5. Audit checklist (entire codebase)

Use this to verify visibility after changes:

- **Admin:** Site Settings (change form), Theme & Experience (/siteconfig/theme-colors/), Feature Control, Report card builder, other siteconfig pages.
- **Backend:** Backend dashboard, entity console, entity import, RBAC, API Center, finance, payroll, requests, analytics, compliance, evals.
- **Portal / Teacher / Parent:** Teacher dashboard, parent dashboard, profile, messages, notifications, portal sidebar, document library, KB, finance (parent), student 360, workflow centers, onboarding wizards.
- **Auth and shared:** Login, school picker, MFA, password change, error pages (403, etc.).

Check with a light theme pack (e.g. Digital Lavender, Campus Blue) and a light backend console theme: no white-on-white; .text-muted, .badge.text-bg-light, and .card boundaries visible everywhere.

---

## 6. Files to touch (summary) – all required, no optionals

| File | Change (all part of the plan) |
|------|-------------------------------|
| `static/css/theme-visibility-guard.css` | Define all visibility values in :root/dark blocks (no hardcoding in rules). Add global .text-muted / .help / .form-text; .badge.text-bg-light; .card border; .theme-experience-page catalog block (mirror Site Settings); dark variants. Use only `var(--vis-*)` / `var(--color-base-*)` / `var(--admin-content-*)`. |
| `static/css/admin-color-preview.css` | Global fallbacks for .theme-pack-catalog, .admin-dashboard-palette-card, and card text using only variables (--vis-*, --color-base-*). |
| `static/css/dashboard-text-visibility.css` | Replace any hardcoded hex with token references (e.g. var(--admin-content-text-muted), var(--vis-text-muted)) so one source of truth. |
| `templates/portal_base.html` | Add data-dashboard-page branch for path containing `/siteconfig/theme-colors` (same script pattern as other pages). |
| `design-tokens.css` (if needed) | Add or confirm canonical values for any token the guard uses (e.g. --admin-content-text-muted) so no raw hex in guard. |
| Docs | Update DASHBOARD_THEME_MASTER_PLAN.md with a one-line note that visibility is enforced codebase-wide via theme-visibility-guard (token-driven, no hardcoding). Keep this plan doc as the single reference. |

---

## 7. Design principle (Unfold + codebase only; no hardcoding)

- **No hardcoding:** All colors, borders, and spacing used for visibility come from design tokens or the guard’s :root. Rules use only `var(--…)`. Canonical values (including final hex/rgba fallbacks) live in one place (design-tokens.css or theme-visibility-guard :root). Change once, apply everywhere.
- **Unfold and codebase only:** All visibility rules use Unfold’s `--color-base-*`, the project’s `--vis-*` and `--admin-content-*` / `--admin-sidebar-*`, and the existing theme hooks. No new theming system or one-off variables.
- **Single guard layer:** theme-visibility-guard.css enforces minimum contrast for shared patterns; dashboard-text-visibility and admin-color-preview reference the same tokens. Same light/dark branching everywhere.
- **All steps in scope:** data-dashboard-page for theme-colors, dashboard-text-visibility alignment, design-tokens audit, and the DASHBOARD_THEME_MASTER_PLAN note are required parts of the plan, not optional.

---

## 8. Long-term and forward-thinking

- **New pages automatically covered:** Any new view that extends `portal_base.html`, `base.html`, or the admin (base_site) already loads `theme-visibility-guard.css`. No per-page CSS for visibility; new dashboards, siteconfig pages, or admin forms get the same contrast guarantees as long as they use the same tokens and classes (.text-muted, .card, .badge.text-bg-light, etc.). Document this in the plan or in a short “Adding new pages” note so future work stays consistent.
- **Single token contract:** Visibility and theming are driven only by (1) design-tokens.css and (2) theme-visibility-guard’s :root/dark blocks. Unfold and theme packs override tokens (e.g. --admin-content-surface); the guard never overrides with raw values. Going forward, any new “visibility” or “contrast” value is added as a token in one of those two places and referenced everywhere via `var(--…)`. No one-off hex in component CSS.
- **Future theme packs and lenses:** New ThemePacks or “lenses” only need to set the existing tokens (--admin-content-*, --color-base-* or Unfold’s equivalents). The guard does not need changes; it already uses those variables. If a new theme still produces low contrast somewhere, fix it by adjusting the token value or adding one rule in the guard that still uses only variables—never by hardcoding a color in that new rule.
- **Optional future automation (out of scope for this plan but aligned):** The codebase’s DASHBOARD_THEME_MASTER_PLAN mentions a “Contrast Auto-Guard” (e.g. WCAG 4.5:1 from background) and theme stress-test matrix (key pages × theme × pack). When you add those later, they should read from the same token set and flag when a token combination fails contrast; the fix remains “change the token,” not “add another hardcoded override.”
- **Documentation as part of the plan:** Update DASHBOARD_THEME_MASTER_PLAN.md (or equivalent) to state that (1) visibility is enforced codebase-wide via theme-visibility-guard, (2) all visibility values are token-driven with no hardcoding, and (3) new pages and new theme packs are covered as long as they use the same template roots and tokens. This keeps the long-term approach visible for future contributors.
