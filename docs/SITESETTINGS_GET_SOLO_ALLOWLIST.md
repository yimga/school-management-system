# SiteSettings.get_solo() — Allowlist

**Purpose:** Tenant-facing code must not call `SiteSettings.get_solo()` or `SiteSettings.load()` for tenant behavior; use `request.tenant_runtime` or `apps.platform_runtime.helpers` (e.g. `get_effective_site_settings(request)`) or `apps.automation.helpers.get_cached_site_settings(school=)`. This document lists every production file where `get_solo()` is **allowed** and the reason. CI enforces zero `get_solo()`/`load()` in tenant apps (see `scripts/lint_tenant_settings.py --check-get-solo-only`). **Migrated:** evals/caching.py previously used `SiteSettings.load()`; now uses `get_cached_site_settings(school=)` (§2.1).

## Allowlisted production paths

| Path | Reason |
|------|--------|
| `apps/siteconfig/models.py` | Definition and internal use of singleton (e.g. `get_solo()` method, default helpers). |
| `apps/platform_runtime/helpers.py` | Canonical shim layer; uses `get_solo()` as platform fallback for `get_effective_site_settings`, `get_effective_flags`, `get_site_display_name`. |
| *(removed)* | ~~apps/platform_runtime/models.py~~ — **B1 done:** `RuntimeDefaults.sync_from_site_settings(site_settings)` now requires callers to pass site_settings; backfill command and SiteSettings.publish_to_runtime_defaults pass it. No get_solo() in this module. |
| *(removed)* | ~~apps/policies/resolver.py~~ — **1.3 done:** Resolver uses `get_effective_site_settings(school=)` only; no get_solo(). |
| *(removed)* | ~~emis/services.py~~ — **Migrated:** `_get_site_for_emis()` uses `get_effective_site_settings(request=, school=)` only; no get_solo(). |
| *(removed)* | ~~apps/siteconfig/forms.py~~ — **Migrated:** ThemeColorsForm accepts `request` in __init__ and uses `get_effective_site_settings(request)` when instance is None; save() uses get_effective_site_settings(request=None) as fallback; no get_solo(). |
| `apps/siteconfig/management/commands/*` | Control-plane / ops only (seed, export, bootstrap). |
| `apps/platform_runtime/management/` | Control-plane / ops only. **backfill_runtime_defaults:** now uses `get_platform_site_settings_record(create=True)` (optional allowlist shrink done); get_solo only in helpers. |
| `apps/finance/management/commands/*` | Control-plane / ops only (preflight, seed_finance_defaults, report_finance_opt_in_gaps). |
| `apps/reports/management/commands/*` | Control-plane / ops only (generate_regional_reports). |

## Test and script paths (excluded from tenant-app lint)

Tests and scripts are excluded from the CI deny-list; they may call `get_solo()` for fixtures and setup. No new production tenant-facing code may call `get_solo()` without being added to the allowlist and this doc.

## Adding a new allowlisted path

1. Add the path to `ALLOWED_GET_SOLO_PREFIXES` in `scripts/lint_tenant_settings.py`.
2. Add a row to the table above with the path and reason.
3. Prefer migrating the call to `get_effective_site_settings(request)` or another runtime helper instead of expanding the allowlist.

## 9.5/10 minimum enforcement

- **Runtime as law:** No new tenant-facing behavior may be driven by direct `SiteSettings` or `get_solo()` reads. New code must use runtime resolvers and precedence (see `docs/architecture/RESOLUTION_CHAIN.md`). CI enforces via `scripts/lint_tenant_settings.py --check-get-solo-only` in `scripts/pre_deploy_gate.sh`; any new allowlist entry must be justified and documented here.
- **Path to 10:** Migrate remaining allowlisted call sites to `get_effective_site_settings(request)` or resolver layer; shrink allowlist over time. To list allowlisted get_solo() usages (migration backlog), run: `python scripts/lint_tenant_settings.py --report-allowlisted --base .`
- **Optional allowlist shrink (BACKLOG §2e row 11):** Prefer adding a thin resolver or helper that wraps `get_solo()` so the allowlist entry points at "resolver/helper" rather than "command calls get_solo directly." **Done:** `backfill_runtime_defaults` now uses `get_platform_site_settings_record(create=True)` and passes that into `RuntimeDefaults.sync_from_site_settings(site_settings)`; get_solo remains only inside helpers (allowlisted). Further shrink: other management commands under platform_runtime/ or siteconfig/ may follow the same pattern when touched.

## References

- `docs/architecture/SITESETTINGS_AUDIT.md`
- `docs/architecture/RESOLUTION_CHAIN.md`
- `docs/PLATFORM_TRANSITION_AUDIT_REPORT.md`
- `apps/platform_runtime/helpers.py` (canonical helpers)
