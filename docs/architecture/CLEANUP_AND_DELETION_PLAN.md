# Cleanup and deletion plan

Explicit list of what to remove or shrink so the platform stays maintainable. Category leaders delete aggressively.

## What to delete or shrink

- **Dead templates:** Unused or superseded templates; remove after confirming no references.
- **Duplicate layout code:** Same layout repeated in multiple templates; replace with shared partials (page_families, shell).
- **Redundant dashboard JS:** Duplicate dashboard logic; consolidate to one dashboard runtime/widget system.
- **Unused formatting helpers:** Duplicate currency/date/number formatting; use one path (runtime.locale, formatters).
- **Legacy settings/config bypasses:** Direct `SiteSettings.get_solo()` or `School.settings`/`School.features` in tenant-facing code; migrate to `request.tenant_runtime` and helpers.
- **Obsolete placeholder TODOs:** Remove or implement; no "TBD" or "TODO" left in production paths.
- **Old admin leftovers:** Remove if superseded by Unfold or custom admin UX.
- **Duplicated currency/date/number logic:** Single formatter layer keyed by runtime.registry and runtime.locale.
- **New code paths that bypass runtime:** Reject in code review; enforce via scripts/check_no_hardcoding.py and scripts/lint_tenant_settings.py.

## What to decompose over time

- **siteconfig:** Split into branding, dashboard engine, workflow engine, platform settings, runtime config helpers, pack governance.
- **Nav/sidebar logic in templates:** Move to control_plane_nav and portal_sidebar_items; templates only render from context.
- **Duplicate dashboard logic:** One dashboard resolver and widget pack system.
- **Duplicated formatting/localization paths:** Single source keyed by runtime.

## What to standardize

- Tables (table-system.css, .table-family, density).
- Forms (form-system.css, sections, validation).
- Cards (card-grammar.css).
- Headers (page_families/title_block).
- Chips/badges (table-status-chip, semantic colors).
- States (empty_state, loading_state, error_state).
- Sidebars (control plane nav, portal sidebar; no hardcoded nav in templates).
- Page families (list, detail, wizard, settings, queue, report, inspector).
- Shell patterns (MarketingShell, ControlPlaneShell, AdminOpsShell, TenantShell).

## CI and enforcement

- `scripts/check_no_hardcoding.py` — fails CI on tenant/country hardcoding.
- `scripts/lint_tenant_settings.py` — reports SiteSettings.get_solo() in tenant apps (--exit-zero).
- Code review: no new god-apps; no direct School.settings/features in tenant-facing code.
- Visual debt: track in docs/VISUAL_DEBT_BACKLOG.md; remediate per page family.

## References

- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md)
- [../VISUAL_DEBT_BACKLOG.md](../VISUAL_DEBT_BACKLOG.md)
- [experience_shells.md](experience_shells.md)
- [page_families.md](page_families.md)
