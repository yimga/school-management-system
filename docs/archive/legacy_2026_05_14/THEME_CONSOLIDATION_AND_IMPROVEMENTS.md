# Theme Consolidation and Improvements

## Goals

- **Consolidate** color and theme sources so one place controls each scope.
- **Close gaps** (e.g. admin using ThemePack without semantic colors).
- **Remove redundancy** (duplicate CSS variables, duplicate fallbacks).
- **Avoid conflicting settings** (clear precedence: Theme Pack vs Site Settings).

---

## Current State: Where Colors Live

| Source | primary | accent | background | header/footer | success/warning/danger |
|--------|---------|--------|------------|--------------|-------------------------|
| **SiteSettings** | ✓ | ✓ | — | ✓ (header_bg, footer_bg) | ✓ |
| **ThemePack** | ✓ | ✓ | ✓ | — | ✗ |
| **ReportCardStyle** | ✓ | ✓ | — | — | — |
| **Evals (models_enhanced)** | ✓ | ✓ | ✓ | — | — |

**Usage:**

- **Portal:** `SITE_THEME` (ThemePack or default) → primary/accent; `SITE` → header/footer.
- **Admin/Backend:** `SITE_ADMIN_THEME` (ThemePack or fallback) → primary/accent/background; **semantic colors** (success/warning/danger) only exist on SiteSettings, so when admin theme is a ThemePack, templates use hardcoded `|default:"#22c55e"` etc.
- **Reports:** ReportCardStyle (per classroom) or SITE fallback.
- **Evals:** Separate model (grading UI); not driven by site theme.

---

## Gaps and Redundancy

1. **Admin semantic colors:** ThemePack has no success/warning/danger. Admin pages use `ADMIN_THEME.success_color|default:"#22c55e"`. When `ADMIN_THEME` is a ThemePack, that’s always the default. **Gap:** semantic colors should come from SiteSettings when ThemePack is used.
2. **Duplicate CSS variable definitions:** `admin/index.html` sets `--brand-primary`, `--brand-accent`, `--brand-success`, etc. in its own `:root`. base_site.html does not set these once for all admin. **Redundancy:** two places can define the same vars with different fallbacks.
3. **Multiple fallback hex values:** Primary/accent use "#667eea", "#ff9f43", "#0d6efd", "#198754" in different templates. **Conflict risk:** inconsistent look if one template is missed.
4. **Color Palette Studio** only applies to primary/accent/background. Site Settings also has header_bg_color, footer_bg_color, success_color, warning_color, danger_color — not covered by the studio “Apply to form” flow.
5. **Admin sidebar active color:** Design tokens and admin_sidebar_enhanced.css set `--admin-sidebar-active-border` to a fixed value. SiteSettings has `admin_sidebar_use_site_primary` but the actual injection of SITE.primary_color into `--admin-sidebar-active-border` may not be in one canonical place.

---

## Consolidation Rules (No Conflicting Settings)

### 1. Single source per scope

- **Portal:** Primary/accent → `SITE_THEME` (ThemePack), fallback `SITE`. Header/footer → `SITE` only.
- **Admin/Backend:** Primary/accent/background → `SITE_ADMIN_THEME` (ThemePack), fallback `SITE`. Success/warning/danger → **always SITE** (SiteSettings), so behaviour is the same whether admin theme is ThemePack or SiteSettings.
- **Reports:** ReportCardStyle; fallback SITE for primary/accent only.
- **Evals:** Own model; no automatic sync with site theme (optional “Copy from Site” in admin later).

### 2. One place to output admin CSS variables

- **base_site.html** outputs a single block that sets:
  - `--brand-primary`, `--brand-accent`, `--surface-deep` (and optionally `--brand-success`, `--brand-warning`, `--brand-danger`) from **resolved** values:
    - Primary/accent/background: from `SITE_ADMIN_THEME` if present, else `SITE`.
    - Success/warning/danger: always from `SITE`.
  - `--admin-sidebar-active-border`: from `SITE.primary_color` when `admin_sidebar_use_site_primary` is True, else from resolved admin theme primary.
- **admin/index.html** (and any other admin template) **does not** redefine these; it uses the variables set in base_site.

### 3. Resolved “admin theme” in context

- Context already has `SITE_ADMIN_THEME` and `SITE`.
- Add a small **resolved** structure (or document the resolution rule in one place):
  - `admin_primary` = SITE_ADMIN_THEME.primary_color if SITE_ADMIN_THEME else SITE.primary_color
  - `admin_accent` = same
  - `admin_background` = SITE_ADMIN_THEME.background_color if SITE_ADMIN_THEME else “#1a1a1a” (or SITE has no background_color, so keep default)
  - `admin_success` = SITE.success_color
  - `admin_warning` = SITE.warning_color
  - `admin_danger` = SITE.danger_color
- Templates then use these resolved values so there is no conflict between ThemePack and SiteSettings.

### 4. Color Palette Studio

- **Site Settings form:** Show “Apply to” for primary, accent, **header**, **footer**, **success**, **warning**, **danger** when those fields exist. Studio already applies to form fields by name; ensure field names match and add buttons/swatches for the extra fields.
- **Theme Pack / Report Card Style:** Keep current behaviour (primary, accent, background only).

### 5. Fallback hex values (canonical)

- Pick one set and use everywhere:
  - Primary: `#0d6efd`
  - Accent: `#198754`
  - Success: `#22c55e`
  - Warning: `#fbbf24`
  - Danger: `#ef4444`
- Replace ad-hoc defaults like `#667eea`, `#ff9f43` in admin with these or with the resolved admin theme.

---

## Implementation Checklist

- [x] **Context: resolved admin theme**  
  In siteconfig context_processors, add `ADMIN_RESOLVED_PRIMARY`, `ADMIN_RESOLVED_ACCENT`, `ADMIN_RESOLVED_BACKGROUND`, `ADMIN_RESOLVED_SUCCESS`, `ADMIN_RESOLVED_WARNING`, `ADMIN_RESOLVED_DANGER` (from SITE_ADMIN_THEME + SITE as above).

- [x] **base_site.html: single injection**  
  In base_site, output a `<style>` that sets `--brand-primary`, `--brand-accent`, `--surface-deep`, `--brand-success`, `--brand-warning`, `--brand-danger`, and (when applicable) `--admin-sidebar-active-border` from resolved values. Use canonical fallbacks.

- [x] **admin/index.html: use variables only**  
  Remove duplicate `:root { --brand-primary: ... }` from admin/index.html; rely on base_site. If index needs extra vars, define only those that are not already set in base_site.

- [x] **Color Palette Studio**  
  In Site Settings, add apply-buttons or harmony swatch actions for `header_bg_color`, `footer_bg_color`, `success_color`, `warning_color`, `danger_color` (when those fields exist). Reuse existing applyToField logic. Studio JS now discovers applicable fields via `getApplicableFields()` and renders one button per field present on the form.

- [ ] **Optional: ThemePack semantic colors**  
  If you want ThemePacks to override success/warning/danger, add optional fields to ThemePack and resolve in context (ThemePack value if set, else SITE). Not required for “no conflicting settings”; only for flexibility.

- [ ] **Docs**  
  Update THEME_PACK_SCOPE.md or equivalent to state: portal uses SITE_THEME + SITE; admin/backend use SITE_ADMIN_THEME + SITE with resolved semantic colors from SITE; one place (base_site) sets admin CSS variables.

---

## Summary

- **Improvements:** Resolved admin theme in context; one place (base_site) for admin CSS variables; Color Palette Studio extended to header/footer/semantic colors in Site Settings; canonical fallback hexes.
- **Consolidation:** Portal = SITE_THEME + SITE; Admin/Backend = SITE_ADMIN_THEME + SITE (semantic from SITE); Reports = ReportCardStyle (+ SITE fallback).
- **Gaps closed:** Admin semantic colors always from SITE; no duplicate admin :root; studio covers all Site Settings color fields.
- **No conflicting settings:** Precedence is explicit (Theme Pack for brand colors when set, Site Settings for semantic and header/footer; base_site is the only injector for admin vars).
