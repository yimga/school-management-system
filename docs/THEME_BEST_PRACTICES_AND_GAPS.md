# Theme Best Practices and Gap Analysis

This document summarizes **best practices** for theme management on the platform and a **thorough audit** of gaps in color palette, button colors, contrast, hover effects, and focus states across CSS and templates.

---

## 1. Best Practices (Recommendations)

### 1.1 Theme management

| Practice | Recommendation |
|---------|----------------|
| **User preference** | Portal and Admin share `localStorage.runmycampus-theme-preference` (light/dark/system). Keep this so one choice follows the user. |
| **Backend** | Keep Backend server-driven (`SITE.backend_console_theme`) so the org can set one theme for the staff console. |
| **Sync attributes** | When changing theme in JS, set both `data-theme` and `data-bs-theme` on `<html>` so Bootstrap and custom CSS stay in sync. |

### 1.2 Color palette

| Practice | Recommendation |
|---------|----------------|
| **Single source of truth** | One canonical “primary” and “accent” for the whole platform. Prefer design-tokens (`--school-primary`, `--school-accent`) overridden by SITE/Theme pack in templates; all other CSS should reference tokens, not competing palettes. |
| **Dark mode** | Use desaturated accents in dark theme (e.g. `--color-primary` lighter in dark) for readability and to avoid vibration. Define in `:root[data-theme="dark"]` / `html[data-bs-theme="dark"]`. |
| **No pure black/white** | Use near-black (e.g. `#0f172a`) and off-white (e.g. `#f1f5f9`) for backgrounds and text. |

### 1.3 Buttons

| Practice | Recommendation |
|---------|----------------|
| **Primary action** | Use a single token (e.g. `var(--school-primary)` or `var(--color-primary)`) for background and border; hover/focus should use a darker or lighter variant from the same system. |
| **Hover/focus** | Every interactive control (button, link, nav pill) should have a visible hover and focus-visible state (e.g. background tint, border, or outline) with a short transition (e.g. 0.2s). |
| **Contrast** | Button text on primary background must meet WCAG AA (4.5:1 for normal text, 3:1 for large). |

### 1.4 Contrast and readability

| Practice | Recommendation |
|---------|----------------|
| **Body text** | Use `--color-text-primary` (or portal/admin equivalent) for body; `--color-text-muted` for secondary. Ensure muted has at least 4.5:1 on background in light, and sufficient contrast in dark. |
| **Muted consistency** | Use one token for “muted” per surface (e.g. `--portal-text-muted`, `--admin-sidebar-text-muted`) so all secondary text is consistent and theme-aware. |
| **Focus ring** | Use one token (e.g. `--focus-ring-color`) for all `:focus-visible` outlines; high contrast in both themes. |

### 1.5 Hover effects

| Practice | Recommendation |
|---------|----------------|
| **Links** | Color shift (e.g. primary → primary-dark) with `transition` on color/background. |
| **Cards / nav pills** | Subtle background or border change, optional light transform (e.g. translateY(-2px)); keep transition short (0.2–0.3s). |
| **Buttons** | Background/border change on hover and focus; do not rely on color alone for state. |

---

## 2. Gaps Found (Audit)

### 2.1 Color palette conflicts

| Issue | Location | Detail |
|-------|----------|--------|
| **Two “primary” palettes** | `design-tokens.css` vs `design-system-unified.css` | Tokens: `--school-primary: #0d6efd` (blue), `--school-accent: #198754` (green). Design-system: `--color-primary: #ff6a88` (pink), `--color-secondary: #9b6bff` (purple), `--color-accent: #2dd4bf` (teal). Portal base injects SITE theme for `--school-primary`; design-system is also loaded and used for links/focus/selection. Result: links and focus can be pink where design-system wins, blue where tokens/portal-modes win. |
| **Portal-specific palette** | `portal_theme.css` | Defines `--sunset-1/2/3`, `--mint-1`, `--sky-1` and uses them for topbar, buttons, nav pills, KPI pills. Not derived from `--school-primary` or `--color-primary`. Branding is decoupled from the rest of the system. |
| **Phase7 duplicate** | `phase7-design-system.css` | Defines `--primary: #007bff`, `--primary-dark: #0d6efd` (Bootstrap-style blue). Not loaded by portal_base or admin base_site; if ever loaded, adds a third primary. |
| **Portal dark nav pill** | `portal-theme-modes.css` | Uses `rgba(102, 126, 234, 0.2)` (indigo) for `--portal-nav-pill-bg-hover` in dark; not from a shared token. |

**Recommendation:** Choose one canonical primary/accent (e.g. SITE + design-tokens) and have design-system-unified and portal_theme reference it (e.g. `--color-primary: var(--school-primary)` in :root, or vice versa). Remove or alias phase7-design-system so it does not introduce a third palette.

### 2.2 Button colors and consistency

| Issue | Location | Detail |
|-------|----------|--------|
| **Portal buttons** | `portal_theme.css` | `.btn-primary` uses gradient `var(--sunset-2), var(--sunset-3)`; `.btn-outline-primary` uses `var(--sunset-3)` and light bg. No use of `--school-primary` or `--color-primary`. |
| **Portal dark buttons** | `portal-theme-modes.css` | `.btn-outline-primary` dark: border `rgba(102, 126, 234, 0.6)`, color `#a5b4fc`; hover bg `rgba(102, 126, 234, 0.25)`. Indigo, not aligned with design-system primary or school primary. |
| **Bootstrap bridge** | `bootstrap-theme-bridge.css` | Sets `--bs-primary: var(--color-primary, #e87995)` in dark. So Bootstrap components use pink in dark; portal_theme overrides .btn-primary with sunset gradient. Inconsistent. |
| **Hover transition** | `portal_theme.css` | `.btn` has `transition: background 120ms ease, border-color 120ms ease, box-shadow 120ms ease`; no transition on color. Outline buttons that change color on hover may snap. |

**Recommendation:** Use one token for primary buttons (e.g. `var(--school-primary)` or SITE-overridden equivalent). Define .btn-primary and .btn-outline-primary (and dark overrides) from that token and a hover variant. Add color to button transition where state changes color.

### 2.3 Focus ring inconsistency

| Issue | Location | Detail |
|-------|----------|--------|
| **Tokens** | `design-tokens.css` | Defines `--focus-ring-color: #0d6efd` and `--focus-ring-offset: 2px` but they are not used consistently. |
| **Design system** | `design-system-unified.css` | `:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }` — uses pink when design-system wins. |
| **Portal dark** | `portal-theme-modes.css` | `:focus-visible { outline: 2px solid #3b82f6 }` (light), `#60a5fa` (dark). Blue, hardcoded. Skip-link and topbar use similar blue. |

**Recommendation:** Use a single focus token everywhere (e.g. `--focus-ring-color`). In design-system-unified and portal-theme-modes, set `:focus-visible { outline: 2px solid var(--focus-ring-color); outline-offset: var(--focus-ring-offset); }` and set `--focus-ring-color` in :root and dark block (e.g. from primary token). Remove hardcoded #3b82f6 / #60a5fa for focus.

### 2.4 Contrast and muted text

| Issue | Location | Detail |
|-------|----------|--------|
| **Muted text variance** | Multiple files | Portal dark: `--portal-text-muted: #94a3b8`. Backend dark: `.text-muted` → `#b8c4d0`. Admin: `--admin-sidebar-text-muted: #cbd5e1`. Three different muted values for dark. |
| **Light mode muted** | `design-system-unified.css` | `--color-text-muted: #4b5563` in light (good for WCAG AA). Default :root has `#6b7280`; light block overrides to `#4b5563`. |
| **Portal light** | `portal-theme-modes.css` | `html[data-bs-theme="light"] body { color: #111827 }`. No explicit muted token for light in portal-theme-modes; relies on design-system or Bootstrap. |
| **Low-contrast spots** | `portal_theme.css` | `.kpi-pill .kpi-label { color: rgba(15, 23, 42, 0.65) }`; `.insight-note` / `.insight-footnote` use `rgba(15, 23, 42, 0.6)`. On light grey bg these may be below 4.5:1. |
| **Table header** | `portal_theme.css` | `table thead th { background: #f8fafc }` — hardcoded; in dark mode this may not be overridden (portal-theme-modes sets .table but not necessarily thead th). |

**Recommendation:** Use one muted token per surface (e.g. `--color-text-muted` or `--portal-text-muted`) and reference it everywhere. In dark, set a single value (e.g. `#94a3b8`) across portal, backend, and admin for consistency. Audit rgba(15,23,42,0.6) and similar for WCAG AA and replace with token or higher-contrast value. Ensure table headers use theme-aware background in portal-theme-modes dark.

### 2.5 Hover effects

| Issue | Location | Detail |
|-------|----------|--------|
| **Card hover** | `portal_theme.css` | `.card:hover` has transform and box-shadow; no transition on color. If card contains links that change color on hover, transition is on link only. Generally OK. |
| **Dropdown hover** | `portal-theme-modes.css` | Dark: `.dropdown-item:hover` uses `rgba(102, 126, 234, 0.25)`. Light: `rgba(13, 110, 253, 0.08)`. Different hues (indigo vs blue); should use same semantic “primary” hover. |
| **Nav pill hover** | `portal_theme.css` | `.nav-pill.active, .nav-pill:hover` use gradient with sunset/purple; no focus-visible style in same file. portal-theme-modes dark overrides with `--portal-nav-pill-bg-hover`. |
| **Admin sidebar** | `admin_sidebar_enhanced.css` | Hover and active use tokens; transitions present. Good. |
| **Backend** | `backend-dark-theme.css` | Link hover `#bfdbfe`; sidebar nav defined. No major gap. |

**Recommendation:** Use one primary hover tint (e.g. from `--school-primary` or `--color-primary` with alpha) for dropdowns, nav pills, and cards in both light and dark. Add focus-visible for nav pills where missing.

### 2.6 Hardcoded colors in templates

| Issue | Location | Detail |
|-------|----------|--------|
| **Inline styles** | 78+ template files | Grep found 1085 hex/rgb/rgba matches in templates. Many are in `<style>` blocks or component markup (e.g. dashboard cards, badges, report styles). |
| **Risk** | Any template | Inline or embedded styles that set color/background directly will not respond to theme or design-token changes. |

**Recommendation:** Prefer CSS classes and tokens over inline color/background in templates. For reports/emails, keep minimal inline styling for email clients; for in-app pages, move colors to CSS using variables.

### 2.7 Load order and overrides

| Observation | Location | Detail |
|-------------|----------|--------|
| **Portal** | `portal_base.html` | Order: design-tokens → design-system-unified → bootstrap-theme-bridge → … → portal_theme → portal-theme-modes. portal_theme and portal-theme-modes override earlier sheets; design-system-unified sets --color-* which bootstrap-theme-bridge uses in dark. |
| **Admin** | `base_site.html` | design-tokens → design-system-unified (no bootstrap-theme-bridge). Admin sidebar vars injected in inline :root after CSS links, so SITE wins. design-system-unified --color-primary (pink) still applies to generic elements (e.g. links) unless overridden by admin-specific CSS. |

**Recommendation:** Document load order in THEME_SYSTEM.md and ensure design-tokens or SITE is the single source for “brand” primary; design-system-unified should alias or use that for --color-primary so links/focus/buttons are consistent.

---

## 3. Summary: Priority Fixes

| Priority | Area | Action |
|----------|------|--------|
| **High** | Palette | Unify primary: either set `--color-primary: var(--school-primary)` in design-system-unified :root (and dark from same source) or retire one of the two. Ensure portal_theme and portal-theme-modes use that token for buttons and nav. |
| **High** | Focus | Use `--focus-ring-color` (and offset) everywhere for :focus-visible; set it from primary token in :root and dark block. Remove hardcoded #3b82f6 / #60a5fa for focus in portal-theme-modes. |
| **Medium** | Buttons | Define .btn-primary / .btn-outline-primary (and dark) from one primary token; add color to transition where hover changes color. |
| **Medium** | Muted text | Use one muted token per surface; align backend and admin muted with portal where possible (#94a3b8 in dark). |
| **Medium** | Contrast | Replace low-contrast rgba text (e.g. .kpi-label, .insight-note) with token or WCAG-safe value; ensure table thead in dark uses theme background. |
| **Low** | Hover | Align dropdown and nav-pill hover tints with primary token (one alpha variant). |
| **Low** | Templates | Gradually replace inline color/background in app templates with classes that use CSS variables. |

---

## 4. File Reference (Quick)

| File | Role |
|------|------|
| `static/css/design-tokens.css` | Shared tokens: --school-primary, --admin-sidebar-*, --portal-*, --backend-*, --focus-ring-color. |
| `static/css/design-system-unified.css` | --color-primary (pink), --color-text-*, spacing, radius, base styles, :focus-visible, dark overrides. |
| `static/css/portal_theme.css` | Portal-specific palette (sunset, mint, sky), topbar, cards, buttons, KPI. |
| `static/css/portal-theme-modes.css` | Dark/light overrides for portal: body, cards, sidebar, forms, tables, dropdowns, buttons, focus. |
| `static/css/bootstrap-theme-bridge.css` | Sets --bs-* in dark from --color-*. |
| `static/css/admin_sidebar_enhanced.css` | Admin sidebar and child block; uses --admin-sidebar-* and theme blocks. |
| `static/css/admin-dark-readability.css` | Admin content area in dark; --admin-content-*. |
| `static/css/backend-dark-theme.css` | Backend dark: body, cards, sidebar, links, forms. |
| `static/css/backend-light-theme.css` | Backend light theme. |
| `static/css/phase7-design-system.css` | Alternate vars (--primary blue); not loaded by portal_base or base_site. |

Applying the high- and medium-priority items above will align color palette, button colors, contrast, and hover/focus behavior across the platform and make future theme changes easier.
