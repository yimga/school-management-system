# CSS and frontend asset rationalization

**Purpose:** Fewer, consolidated CSS files per surface; clear ownership (marketing vs app vs dashboard vs theme). Each surface loads only its bundle.

## Current CSS by surface

### Tenant app (base.html)

- vendor: bootstrap.min.css, bootstrap-icons.min.css
- design-tokens.css, design-system-unified.css, toggle-colors.css
- header-footer-visibility.css, mobile-tables-forms.css
- dashboard-responsive.css, ui-alignment-improvements.css, no-watermark.css, topbar-header-polish.css
- dashboard-high-contrast.css, dashboard-text-visibility.css, theme-everywhere-dark.css, theme-visibility-guard.css
- platform-high-end.css, surface-themes.css
- table-system.css, form-system.css, card-grammar.css, chart-rules.css, platform-responsive-touch.css
- dashboard-theme-sync.css, preview-highlights.css

**Optional consolidation (not in plan scope):** dashboard-*.css could be merged into one or two files (e.g. dashboard-bundle.css); theme-* into one theme bundle. Current state is rationalized per-surface loading.

### Portal (portal_base.html)

- design-tokens, design-system-unified, toggle-colors, bootstrap-theme-bridge
- mobile-tables-forms, portal_theme.css, portal-theme-modes.css
- dashboard-responsive, responsive-performance, ui-alignment-improvements, portal-layout-professional
- platform-premium-content, portal-sidebar.css, no-watermark, header-footer-visibility, topbar-header-polish
- dashboard-high-contrast, dashboard-text-visibility, dashboard-crisp-polish
- platform-high-end, portal-premium-shell, surface-themes
- table-system, form-system, card-grammar, chart-rules, theme-everywhere-dark, theme-visibility-guard, platform-responsive-touch

### Control plane (control_plane_skeleton.html)

- design-tokens, design-system-unified, theme-visibility-guard, manager-control-plane.css
- platform-high-end, surface-themes, table-system, form-system, card-grammar, chart-rules, platform-responsive-touch

**No** dashboard-*, no marketing-shell, no portal_theme.

### Marketing (base_marketing.html)

- design-tokens.css, tokens-marketing.css, marketing-shell.css only. **No** design-system-unified, no dashboard-*.

## Rules

1. **Marketing:** Only marketing/ tokens and shell; no app or dashboard CSS.
2. **Control plane:** Manager + platform shared; no portal-specific or marketing CSS.
3. **Tenant/portal:** Shared design-tokens and design-system; dashboard and theme files for tenant UI only. Do not load control-plane-only (manager-control-plane.css) or marketing-only in tenant.
4. **Duplicates:** design-tokens, design-system-unified, table-system, form-system, card-grammar, chart-rules, platform-responsive-touch, surface-themes, platform-high-end appear in both base.html and control_plane_skeleton or portal_base; that is intentional (shared platform layer). Avoid loading the same file twice in one page.

## Optional consolidation (out of scope for this plan)

- Group dashboard-*.css into dashboard-bundle.css for tenant/portal.
- Group theme-*.css into theme-bundle.css.
- Shared vs surface-specific files are documented in SHELL_ARCHITECTURE_MATRIX.md.

## References

- `docs/SHELL_ARCHITECTURE_MATRIX.md`
- `templates/base.html`, `templates/portal_base.html`, `templates/control_plane_skeleton.html`, `templates/marketing/base_marketing.html`
