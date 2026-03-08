# Tenancy and Global Defaults (Phase 12)

**Rule:** Schema-per-tenant is the primary tenancy model. Session variables are used only for audit, tracing, and impersonation. No regional/hardcoded defaults in settings or code; use registries and runtime.

## Settings cleanup

- Do not add defaults in `config/settings.py` that encode country/currency/grading (e.g. `REGION_CODE='CMR'`, `DEFAULT_GRADING_SCALE='0-20'`, `DEFAULT_CURRENCY='XAF'`).
- Use env only for infrastructure; bootstrap defaults come from registries or first-run seed.

## Code sweeps

- **Constants:** Replace literal country codes, currencies, grading scales with registry-driven or runtime resolution.
- **Forms/templates:** Dropdowns and labels for country, subdivision, education level, terminology from registries via `request.tenant_runtime.registry`.
- **Conditionals:** Replace `if country == ...` / `if school_type == ...` with policy evaluation or `runtime.modules.*`.

## CI / lint

- Flag patterns: `DEFAULT_COUNTRY`, `COUNTRY_`, `if country ==`, `SiteSettings.get_solo()` in tenant code paths, direct `School.settings`/`School.features`.
- Pre-commit or CI step should warn or fail as agreed.

## Test matrix

- Use blueprint- and registry-driven fixtures; tests grouped by blueprint family (e.g. Cameroon Francophone/Anglophone, UAE, UK, US, Brazil, Germany, Saudi RTL, tertiary, technical).
- Avoid Cameroon-only or single-region defaults in core tests.
