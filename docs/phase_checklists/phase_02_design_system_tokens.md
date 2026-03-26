# Phase 2 — Design system + token enforcement — checklist

**SOT:** ZIP Phase 2 — COMPLETE (repository ship gate). Per-template drift is **continuous** (§11.4, Phase H).

## Scripts / docs

- [x] `scripts/verify_design_system_phase2.py` — run after CSS/template changes (includes `studio-system-config-console.css`)
- [x] `docs/DESIGN_SYSTEM_PHASE2.md` — canonical reference
- [x] `scripts/verify_ux_completion.py` — PASS (2026-03-24, post portal shell + bridge + Studio control CSS)

## Studio / sysconf (2026-03-24)

- [x] `static/css/studio-system-config-console.css` — token-based sysconf hero + cards (replaces template inline `<style>`)
- [x] `templates/studio_os/partials/shell_extrastyle.html` — links sysconf CSS for all Studio loads
- [x] `static/css/studio-shell-layout.css` — `.studio-os-subpage-canvas` surfaces

## Control plane skeleton + base (2026-03-24)

- [x] `static/css/control-plane-skeleton-root.css` — replaces inline `<style>` in `control_plane_skeleton.html` (`:root` bridge + overflow-x clip)
- [x] `templates/control_plane_base.html` — navbar / search / sidebar / offcanvas surfaces via classes; rules in `manager-control-plane.css`

## Remaining drift (track next batch)

- [x] `templates/admin/base_site.html` — layout/preview/sidebar rules → `admin-base-site-shell.css`; **only** `#admin-brand-resolved-tokens` remains (Django `--brand-success|warning|danger`)
- [x] `templates/control_plane_base.html` — keyboard overlay + panel + tour FAB → `manager-control-plane.css` (`.cp-keyboard-help-*`, `.cp-tour-fab`)

## Canonical bases (tokens load + enforcement)

- [x] `templates/control_plane_base.html` / skeleton — uses token variables per Phase 2 doc
- [x] `templates/portal_base.html` / `base.html`
- [x] `templates/admin/base_site.html` (manager) — phase1 + design tokens where specified
- [x] `static/css/studio-shell-layout.css` — Studio layout extracted from improvisation

## Touched surfaces (re-verify when editing)

- [x] `python scripts/report_template_inline_styles.py` — gate: **0 flagged** non-exempt `<style>` blocks (re-run after template CSS edits)
- [ ] Card / form / table / alert patterns — match DESIGN_SYSTEM_PHASE2 component grammar (continuous on new pages)

## Tenant portal + marketing + shared chrome (2026-03-24 breadth)

- [x] `static/css/portal-base-shell.css` — bulk rules from `portal_base.html` (theme :root + optional heading font + `data-site-custom-css` stay in template)
- [x] `portal_base.html` — `portal-sidebar-tone-dark` / `portal-sidebar-tone-light` on `<body>` for server default sidebar surface
- [x] `templates/marketing/base_marketing.html` — PUBLIC_BRAND tokens on `<html style="...">` (no inline style element)
- [x] `static/css/admin-nav-bridge-tenant.css` + manager bridge uses `cp-navbar--surface` / shared CP search classes
- [x] `static/css/studio-control-mode-canvas.css` + `shell_extrastyle.html` link
- [x] `static/css/root-base-shell.css` + `templates/base.html` — static shell; prefs on `<html>`; `#root-base-theme-vars` for Django theme
- [x] `static/css/portal-ui-components.css` — consolidated `templates/components/*.html` + `partials/language_switcher.html`
- [x] `static/css/phase2-static-templates-bundle.css` — static-only template extractions (`scripts/extract_template_styles_phase2.py`)
- [x] `static/css/badge-verify.css` + `#badge-verify-theme-vars`; `reportcard-style-preview-shell.css` + `#reportcard-preview-theme-vars`
- [x] `portal_base`, `base`, `admin/base_site`, `control_plane_skeleton`, `marketing/base_marketing` link shared component + phase2 bundles
- [x] `scripts/report_template_inline_styles.py` — **0 flagged** non-exempt blocks; five **server-theme** templates documented in script (`admin/index.html`, `admin/index_tenant.html`, `admin/admin_dashboard.html`, `accounts/backend_dashboard.html`, `customersuccess/guided_onboarding.html`)

## Validation

- [x] `python scripts/verify_design_system_phase2.py` — PASS (includes new required static files)
- [x] `python scripts/verify_ux_completion.py` — PASS

## Acceptance

- [x] Ship gate: tokens + enforcement script (SOT)
- [x] Phase 2 template `<style>` closure: report script shows **0 flagged**; regenerate static bundles only via `extract_template_styles_phase2.py` when adding **static-only** blocks
