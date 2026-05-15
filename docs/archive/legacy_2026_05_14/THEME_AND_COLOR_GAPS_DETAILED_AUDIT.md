# Theme & Color Gaps – Detailed Audit

This document lists **every** identified gap with file paths, line numbers, selectors, current values, and concrete fix recommendations. Use it as a checklist for implementation.

---

## 1. Palette / Primary Conflict

Different “primary” and accent definitions exist across files. Which one wins depends on load order and context.

| File | Lines | Selector / Variable | Current Value | Issue |
|------|-------|---------------------|---------------|-------|
| `static/css/design-tokens.css` | 9–12 | `:root` | `--school-primary: #0d6efd`, `--school-accent: #198754` | Blue/green brand |
| `static/css/design-system-unified.css` | 13–15 | `:root` | `--color-primary: #ff6a88`, `--color-primary-dark: #ff3b5f` | Pink (Gilead 2026) |
| `static/css/design-system-unified.css` | 182–184 | `html[data-bs-theme="dark"]` | `--color-primary: #e87995` | Dark-mode pink |
| `static/css/portal_theme.css` | 2–6 | `:root` | `--sunset-1/2/3`, `--mint-1`, `--sky-1` (e.g. `#ff6a88`, `#a04bfe`) | Separate palette, not tied to `--color-primary` |
| `static/css/phase7-design-system.css` | 9–11 | `:root` | `--primary: #007bff`, `--primary-dark: #0d6efd` | Bootstrap blue; competes with design-system-unified |
| `static/css/bootstrap-theme-bridge.css` | 25 | (bridge) | `--bs-primary: var(--color-primary, #e87995)` | Maps BS to `--color-primary`; fallback is pink |

**Recommendation**

- **Single source of truth:** Decide one canonical primary (e.g. Gilead pink `#ff6a88` / `#e87995` dark).
- In `design-tokens.css`: either remove `--school-primary` / `--school-accent` or alias them to the canonical primary (e.g. `--school-primary: var(--color-primary);`).
- In `portal_theme.css`: replace raw `--sunset-*` / `--mint-*` / `--sky-*` usage for **primary** actions with `var(--color-primary)` (and `--color-secondary`, `--color-accent` where appropriate). Keep sunset/mint/sky only for decorative or secondary roles.
- In `phase7-design-system.css`: set `--primary` and `--primary-dark` to `var(--color-primary)` and `var(--color-primary-dark)` so one file controls the hue; or remove phase7 if it’s redundant with design-system-unified.

---

## 2. Focus Ring Inconsistency

Multiple `:focus-visible` rules use different colors and tokens. Last-loaded rule wins; behavior varies by section (admin vs portal vs global).

| File | Lines | Selector | Current Value | Issue |
|------|-------|----------|---------------|-------|
| `static/css/design-tokens.css` | 86–87 | (variables only) | `--focus-ring-color: #0d6efd`, `--focus-ring-offset: 2px` | Defined but **not used** by all focus rules |
| `static/css/design-system-unified.css` | 280–282 | `:focus-visible` | `outline: 2px solid var(--color-primary); outline-offset: 2px` | Uses pink primary |
| `static/css/admin_theme.css` | 197–202 | `#nav-sidebar .module li a:focus-visible`, `.button:focus-visible`, `.submit-row input:focus-visible` | `outline: 2px solid var(--color-primary); outline-offset: var(--spacing-xs)` | Same token, admin context |
| `static/css/admin_sidebar_enhanced.css` | 158–161 | `.sidebar-collapse-toggle:focus-visible` | `outline: 2px solid #fff; outline-offset: 2px` | **Hardcoded white** – fine on dark sidebar, fails on light theme |
| `static/css/portal-theme-modes.css` | 33–39 | `:focus-visible`, `html[data-bs-theme="dark"] :focus-visible` | Light: `#3b82f6`; Dark: `#60a5fa` | **Hardcoded blue** – overrides design-system-unified when this file loads after |
| `static/css/portal-theme-modes.css` | 287–294 | `#themeToggle:focus-visible`, `.topbar-controls .btn-link:focus-visible`, `.topbar-controls .btn:focus-visible` | `outline: 2px solid rgba(255,255,255,0.9)` | White for topbar only – OK |
| `static/css/phase7-design-system.css` | 362–365 | `:focus-visible` | `outline: 2px solid var(--primary); outline-offset: 2px` | Uses `--primary` (blue in phase7) |

**Recommendation**

- Use a **single focus token** everywhere: e.g. `--focus-ring-color` and `--focus-ring-offset` from `design-tokens.css`, and in dark mode set `--focus-ring-color` to a visible color (e.g. `#60a5fa` or `var(--color-primary)`).
- In **design-system-unified.css** and **phase7-design-system.css**: set `:focus-visible` to `outline: 2px solid var(--focus-ring-color); outline-offset: var(--focus-ring-offset, 2px);`.
- In **portal-theme-modes.css**: remove the global `:focus-visible` / `html[data-bs-theme="dark"] :focus-visible` overrides (lines 33–39), or replace with `--focus-ring-color` / `--focus-ring-offset` overrides only (no duplicate outline rules).
- In **admin_sidebar_enhanced.css**: replace `#fff` with a variable, e.g. `var(--admin-sidebar-focus-ring, #fff)` and set that in admin light/dark theme so it’s white on dark and dark on light.

---

## 3. Button Inconsistency

`.btn-primary` and `.btn-outline-primary` are defined in several places with different colors and semantics.

| File | Lines | Selector | Current Value | Issue |
|------|-------|----------|---------------|-------|
| `static/css/portal_theme.css` | 112–121 | `.btn-primary`, `.btn-outline-primary:hover` | Gradient `linear-gradient(135deg, var(--sunset-2), var(--sunset-3))` | **Not** using `--color-primary` |
| `static/css/portal_theme.css` | 119–121 | `.btn-outline-primary` | `color: var(--sunset-3); border-color: rgba(160,75,254,0.35); background: #f7f9fc` | Hardcoded purple tint and light bg |
| `static/css/portal-theme-modes.css` | 252–258 | `html[data-bs-theme="dark"] .btn-outline-primary`, `:hover` | `border-color: rgba(102,126,234,0.6); color: #a5b4fc` / hover `rgba(102,126,234,0.25); color: #c7d2fe` | **Indigo** – doesn’t match portal_theme sunset/purple |
| `static/css/admin-components.css` | 310–313, 332–372 | `.btn-primary`, `.btn-outline-primary` | Use `var(--color-primary)` | Consistent with design-system-unified |
| `static/css/backend-light-theme.css` | 60–78 | `.btn-outline-primary`, `.btn-primary` | Custom backend colors | Backend-specific; ensure they use tokens |
| `static/css/backend-dark-theme.css` | 132–151 | Same | Same | Same |
| `static/css/phase7-design-system.css` | 337–344 | `.btn-primary`, `.btn-primary:hover` | `var(--primary)`, `var(--primary-dark)` | Uses phase7 blue |

**Recommendation**

- **Portal:** In `portal_theme.css`, change `.btn-primary` (and primary hover) to use `var(--color-primary)` / `var(--color-primary-dark)` (and gradient only if you explicitly want it, e.g. `linear-gradient(135deg, var(--color-primary), var(--color-secondary))`). For `.btn-outline-primary`, use `border-color: var(--color-primary); color: var(--color-primary);` and a theme-aware background (e.g. `var(--color-bg-primary)` or `transparent`).
- **Portal dark:** In `portal-theme-modes.css`, change `.btn-outline-primary` (and hover) to use `var(--color-primary)` / `var(--color-primary-dark)` (or `var(--color-primary-light)`) instead of indigo `#a5b4fc` / `rgba(102,126,234,...)` so portal stays on one palette.
- **Phase7:** If kept, make `.btn-primary` use `var(--color-primary)` by setting `--primary` to `var(--color-primary)` in that file or by not loading phase7 after design-system-unified with conflicting primaries.

---

## 4. Contrast & Muted Text Variance

Muted/secondary text uses different hex values per area; some may fail WCAG AA on certain backgrounds.

| File | Lines | Context | Current Value | Note |
|------|-------|---------|---------------|------|
| `static/css/design-tokens.css` | 23, 38 | Admin default, Portal light | `--admin-sidebar-text-muted: #cbd5e1`, `--portal-text-muted: #6c757d` | OK |
| `static/css/design-tokens.css` | 99 | Dark overlay | `--overlay-text-muted: #94a3b8` | OK |
| `static/css/design-system-unified.css` | 30, 159, 175 | Light / light WCAG / dark | `--color-text-muted: #6b7280`, `#4b5563`, `#94a3b8` | Slight variance light vs “WCAG” |
| `static/css/admin_sidebar_enhanced.css` | 11, 33, 46, 57, 70 | Admin dark/light/child | `#cbd5e1`, `#e2e8f0`, `#475569`, etc. | Themed; ensure contrast on child blocks |
| `static/css/admin-dark-readability.css` | 22, 54, 148, 171, 186 | Admin dark content | `#cbd5e1` (and hardcoded in selectors) | Multiple hardcoded `#cbd5e1` |
| `static/css/backend-dark-theme.css` | 25–28, 76, 98, 102, 121, 225, 281, 297–298, 310 | Backend dark | `#b8c4d0`, `#cbd5e1`, `#94a3b8` | **Three** different muted shades in one theme |
| `static/css/admin-content-readability.css` | 72, 82, 113, 191, 228, 249 | Admin content light/dark | `#cbd5e1`, `#475569`, `#94a3b8` | Mixed |
| `static/css/admin-polish.css` | 207, 236, 258, 264 | Admin | `#94a3b8`, `#cbd5e1` | Overrides sidebar muted |
| `static/css/portal-theme-modes.css` | 46, 51, 97, 124, 132, 145–151, 165, 197, 264, 381–382 | Portal dark/classic | `--portal-text-muted: #94a3b8`, `#cbd5e1` for nav-pill, `#6b7280` classic | Portal muted consistent; classic uses different token |

**Recommendation**

- **Naming:** Use one token per “role” per theme, e.g. `--text-muted` (or `--portal-text-muted` / `--admin-sidebar-text-muted`) and in dark mode set it once (e.g. `#94a3b8` or `#b8c4d0`) so all areas that should look “muted” use the same variable.
- **Backend dark:** Replace the mix of `#b8c4d0`, `#cbd5e1`, and `#94a3b8` with a single `--backend-text-muted` (e.g. `#94a3b8`) and use it everywhere for `.text-muted` and secondary text in backend-dark-theme.css.
- **WCAG:** Keep `design-system-unified.css` light “stronger contrast” override (`#4b5563`) for light mode; ensure dark muted (e.g. `#94a3b8`) passes 4.5:1 (or 3:1 for large text) on the dark backgrounds used (e.g. `#1e293b`, `#0f172a`).

---

## 5. Hardcoded Colors in portal_theme.css (Tables, Labels, rgba)

| File | Lines | Selector | Current Value | Issue |
|------|-------|----------|---------------|-------|
| `static/css/portal_theme.css` | 150 | `.kpi-pill .kpi-label` | `color: rgba(15, 23, 42, 0.65)` | May be low contrast on some cards; use token |
| `static/css/portal_theme.css` | 255, 261–262 | `.insight-pill-row`, `.insight-note`, `.insight-footnote` | `color: rgba(15, 23, 42, 0.7)` / `0.6` | Not theme-aware for dark mode |
| `static/css/portal_theme.css` | 273–277 | `table thead th` | `background: #f8fafc` | Hardcoded light; dark mode needs override |
| `static/css/portal_theme.css` | 248 | `.subject-list li` | `color: #475569` | Should use `var(--color-text-muted)` or portal equivalent |

**Recommendation**

- Replace with tokens: e.g. `--portal-text-muted` or `--color-text-muted` for labels and footnotes; for `table thead th` use `var(--color-bg-light)` or `var(--portal-bg)` and add a dark-mode override in portal-theme-modes.css (e.g. `background: var(--color-bg-light)` where dark theme sets that variable).

---

## 6. Hover Effect Inconsistencies (Dropdown, Nav-Pill)

| File | Lines | Selector | Current Value | Issue |
|------|-------|----------|---------------|-------|
| `static/css/portal-theme-modes.css` | 53–54 | `html[data-bs-theme="dark"]` | `--portal-nav-pill-bg-hover: rgba(102,126,234,0.2)`, `--portal-nav-pill-bg-active: rgba(102,126,234,0.25)` | Indigo; rest of portal uses sunset/purple/pink |
| `static/css/portal-theme-modes.css` | 189–191 | `.dropdown-item:hover`, `.dropdown-item:focus` | `background: rgba(102,126,234,0.25); color: #f1f5f9` | Same indigo |

**Recommendation**

- Use primary/secondary from design system: e.g. `--portal-nav-pill-bg-hover: rgba(var(--color-primary-rgb, 255, 106, 136), 0.2)` or a single `--portal-nav-pill-active-bg` set to a primary-based color. Same for `.dropdown-item:hover`/`:focus` (e.g. `var(--color-primary-light)` or a dedicated dropdown hover token).

---

## 7. Hardcoded Inline Styles in Templates

These prevent theme responsiveness and reuse. Prefer CSS classes and variables.

| Template | Line (approx) | Snippet / Purpose | Recommendation |
|----------|----------------|-------------------|----------------|
| `templates/admin/components/admin_theme_preset.html` | 2, 4 | Border `#ddd`, background `#fafafa`, text `#666` | Use CSS classes and variables (e.g. `--border-color`, `--body-bg`) or remove inline |
| `templates/admin/admin_dashboard.html` | 211, 239–241, 252–253, 266, 268, 282–298, 306, 310, 350, 382 | Stats colors `#4c51bf`, `#3182ce`, `#38a169`, gradients `#667eea`/`#764ba2`, `#dc3545`, `#667eea`/`#764ba2`, etc. | Move to CSS; use `--color-primary`, `--color-success`, `--color-danger`, or utility classes |
| `templates/portal_base.html` | 686, 688 | Search/topbar `rgba(255,255,255,0.15)`, hint `rgba(255,255,255,0.85)` | Use vars e.g. `--topbar-input-bg`, `--topbar-input-hint` |
| `templates/backend_base.html` | 41 | Activity item `rgba(99,102,241,0.5)` | Use var e.g. `--sidebar-activity-accent` |
| `templates/teacher/dashboard.html` | 314, 325 | Donut `--accent: #22c55e`, `#6d28d9` | Use `var(--color-success)` and `var(--color-secondary)` or theme vars |
| `templates/parent/dashboard.html` | 1004 | Card border/background rgba | Use class + CSS vars |
| `templates/widgets/finance_dashboard_widgets.html` | 4 | `linear-gradient(135deg,#0d6efd,#198754)` | Use `var(--school-primary)` / `var(--school-accent)` or design-system primary/accent |
| `templates/teacher/workflow_center.html` | 110 | Border `rgba(148,163,184,0.2)` | Use `var(--portal-border)` or `var(--color-border)` |
| `templates/siteconfig/feature_control_panel.html` | 60 | `#f8f9fa` | Use `var(--bs-tertiary-bg)` or design-system var |
| `templates/reports/term_report_cameroon.html` | 266 | `color: #555` | Use muted token |
| `templates/reports/annual_report_cameroon.html` | 229 | `color: #666` | Same |
| `templates/portal/kb_home.html` | 13 | Gradient with `var(--school-primary, #0d6efd)` | OK if school primary is canonical; else align with `--color-primary` |
| `templates/partials/portal_sidebar.html` | 520 | `rgba(99,102,241,0.5)` | Same as backend_base – use shared var |
| `templates/parent/workflow_center.html` | 110 | Same as teacher | Same |
| `templates/home.html` | 14, 21 | Card bg `rgba(13,110,253,.06)`, `rgba(255,122,24,.08)` | Use utility classes or vars (e.g. primary/attention tint) |
| `templates/finance/dashboard.html` | 53–56 | Buttons `rgba(255,255,255,0.1)` | Use class e.g. `.btn-hero-overlay` with var |
| `templates/emails/report_ready_en.html` | 25 | `primary_color|default:'#0d6efd'` | Keep server-driven; ensure default matches canonical primary |
| `templates/emails/base_branded.html` | 18 | Same | Same |
| `templates/components/weather_widget.html` | 3, 6–7, 13–14, 20 | Orange/blue tints, `#1e293b`, `#64748b`, `#475569`, `#ff9500` | Use design-system text/background vars and one accent var |
| `templates/components/user_dropdown.html` | 10 | Gradient `#667eea`/`#764ba2` | Use `var(--color-primary)` / `var(--color-secondary)` or one gradient var |
| `templates/components/student_360_tabs.html` | 450, 454 | `#2dd4bf`, `#ff6a88` | Use `var(--color-accent)` and `var(--color-primary)` |
| `templates/components/recent_activity.html` | 5 | Gradient `#667eea`/`#764ba2` | Same as user_dropdown |
| `templates/components/logo_watermark.html` | 51 | `rgba(13, 110, 253, 0.1)` | Use `var(--school-primary)` with alpha or a “watermark-bg” var |
| `templates/components/logo_admin_settings.html` | 48, 63 | `#f8f9fa`, `#e7f3ff`, `#0d6efd` | Use design-system or BS vars |
| `templates/components/dashboard_header.html` | 13 | Gradient `#0d6efd`, `#6366f1` | Use primary/secondary vars |
| `templates/accounts/workflow_center.html` | 115 | Border `rgba(148,163,184,0.2)` | Use `var(--portal-border)` |
| `templates/accounts/profile.html` | 24 | `rgba(13,110,253,.12)` | Use primary tint var |

**Recommendation**

- Introduce small utility classes (e.g. `.bg-primary-tint`, `.text-stat-success`, `.card-hero`) and/or CSS custom properties in a single file (e.g. `--stat-success`, `--hero-btn-bg`) and replace inline styles with classes/vars. Do this in phases: admin dashboard first, then shared components, then portal/backend.

---

## 8. CSS Load Order and Overrides

Load order determines which variables and focus/button rules win.

**Admin (`templates/admin/base_site.html`):**

1. design-tokens.css  
2. design-system-unified.css  
3. admin-components.css  
4. admin_theme.css  
5. admin_sidebar_enhanced.css  
6. admin-dark-readability.css  
7. admin-dashboard.css  
8. dashboard-responsive.css  
9. Bootstrap 5.3  
10. Font Awesome  

So: **design-system-unified** sets `--color-primary` (pink); **design-tokens** sets `--school-primary` (blue) and `--focus-ring-color` (blue) but focus **outline** is applied in design-system-unified and admin_theme; **admin_sidebar_enhanced** overrides focus for `.sidebar-collapse-toggle` with white.

**Portal (`templates/portal_base.html`):**

1. Bootstrap, Bootstrap Icons  
2. design-tokens.css  
3. design-system-unified.css  
4. bootstrap-theme-bridge.css  
5. mobile-tables-forms.css  
6. portal_theme.css  
7. **portal-theme-modes.css**  
8. dashboard-responsive.css, etc.  

So: **portal-theme-modes.css** overrides **design-system-unified** for global `:focus-visible` (blue) and for `.btn-outline-primary` (indigo). **portal_theme.css** sets its own button and palette (sunset/mint/sky) and does not use `--color-primary` for buttons.

**Backend:** Extends `portal_base.html`, then adds dashboard-layout-*.css and either backend-light-theme.css or backend-dark-theme.css. So backend gets all portal CSS first; backend-*-theme.css overrides for `.btn-*`, `.text-muted`, etc.

**Recommendation**

- Document the intended “winning” source for: (1) primary/accent palette, (2) focus ring, (3) button styles, (4) muted text. Then remove or narrow overrides so that:
  - One file (e.g. design-tokens.css + design-system-unified.css) sets palette and focus tokens.
  - Portal and admin only override where necessary (e.g. admin sidebar focus, portal topbar focus) using those tokens.
  - Portal buttons and nav-pill/dropdown hovers use the same primary/secondary tokens as the rest of the app.

---

## 9. Phase7 vs Design-System-Unified

| Aspect | phase7-design-system.css | design-system-unified.css |
|--------|---------------------------|----------------------------|
| Primary | `--primary: #007bff` (blue) | `--color-primary: #ff6a88` (pink) |
| Focus | `:focus-visible` uses `var(--primary)` | Uses `var(--color-primary)` |
| Buttons | `.btn-primary` uses `var(--primary)` | (Admin/components use `var(--color-primary)`) |

Phase7 is not in the admin or portal base template link lists above; if it’s included elsewhere (e.g. a specific app or page), it will override design-system-unified when loaded after. Prefer a single design system file and retire phase7 or make it only set aliases (e.g. `--primary: var(--color-primary);`) and no competing rules.

---

## 10. Summary Checklist

- [ ] **Palette:** One canonical primary (e.g. `--color-primary`); alias `--school-primary` and phase7 `--primary` to it; portal_theme buttons use it.
- [ ] **Focus:** Single `--focus-ring-color` / `--focus-ring-offset`; all `:focus-visible` use them; admin sidebar toggle uses theme-aware var; remove duplicate global focus rules in portal-theme-modes.
- [ ] **Buttons:** Portal and portal dark use `--color-primary` / `--color-primary-dark` for `.btn-primary` and `.btn-outline-primary`; align nav-pill and dropdown hover with same palette.
- [ ] **Muted text:** One token per context (portal, admin, backend); backend dark uses one `--backend-text-muted`; verify WCAG on chosen values.
- [ ] **portal_theme.css:** Table header, labels, footnotes use tokens; dark overrides for tables and rgba text.
- [ ] **Templates:** Replace inline hex/rgba with classes and CSS variables (prioritize admin dashboard and shared components).
- [ ] **Load order:** Document and enforce “design-tokens + design-system-unified first”; theme-specific files only override tokens or add scoped rules.
- [ ] **Phase7:** Remove or alias to design-system-unified so only one design system controls primary and focus.

Once these are done, theme and color behavior will be consistent and easier to maintain.
