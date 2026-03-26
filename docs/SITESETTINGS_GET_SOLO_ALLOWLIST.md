# SiteSettings.get_solo() — Allowlist

**Purpose:** Tenant-facing code must not call `SiteSettings.get_solo()` or `SiteSettings.load()` for tenant behavior; use `request.tenant_runtime` or `apps.platform_runtime.helpers` (e.g. `get_effective_site_settings(request)`) or `apps.automation.helpers.get_cached_site_settings(school=)`. This document lists every production file where `get_solo()` is **allowed** and the reason. CI enforces zero `get_solo()`/`load()` in tenant apps (see `scripts/lint_tenant_settings.py --check-get-solo-only`). **Migrated:** evals/caching.py previously used `SiteSettings.load()`; now uses `get_cached_site_settings(school=)` (§2.1).

## `SiteSettings.objects.*` ORM choke point (Phase 6 / 7)

**Rule:** Outside migrations, tests, and `management/commands/`, only these files may contain `SiteSettings.objects.`:

| Path | Reason |
|------|--------|
| `apps/siteconfig/models.py` | `SiteSettings.get_solo()` implementation (`get_or_create`, etc.). |
| `apps/platform_runtime/helpers.py` | `get_platform_site_settings_record()` and related platform singleton access. |

**Everyone else** (tenant apps, Studio OS, super views, Django admin classes, `brand_experience`, etc.) must use **`get_platform_site_settings_record(create=True|False)`** or **`get_effective_site_settings(...)`**, not raw `SiteSettings.objects`.

**CI:** `python scripts/lint_sitesettings_orm_singleton.py --base .` — also bundled in `scripts/verify_cursor_phase6_siteconfig_sitesettings.py` and `scripts/verify_cursor_phase7_granular.py`.

## Allowlisted production paths (`get_solo` / legacy naming)

| Path | Reason |
|------|--------|
| `apps/siteconfig/models.py` | Definition and internal use of singleton (e.g. `get_solo()` method, default helpers). |
| `apps/platform_runtime/helpers.py` | Canonical shim layer; platform singleton access for `get_effective_site_settings`, `get_effective_flags`, `get_site_display_name`, `get_platform_site_settings_record`. |
| *(removed)* | ~~apps/platform_runtime/models.py~~ — **B1 done:** `RuntimeDefaults.sync_from_site_settings(site_settings)` now requires callers to pass site_settings; backfill command and SiteSettings.publish_to_runtime_defaults pass it. No get_solo() in this module. |
| *(removed)* | ~~apps/policies/resolver.py~~ — **1.3 done:** Resolver uses `get_effective_site_settings(school=)` only; no get_solo(). |
| *(removed)* | ~~emis/services.py~~ — **Migrated:** `_get_site_for_emis()` uses `get_effective_site_settings(request=, school=)` only; no get_solo(). |
| *(removed)* | ~~apps/siteconfig/forms.py~~ — **Migrated:** ThemeColorsForm accepts `request` in __init__ and uses `get_effective_site_settings(request)` when instance is None; save() uses get_effective_site_settings(request=None) as fallback; no get_solo(). |
| *(removed)* | ~~management command trees~~ — **Allowlist shrunk (2026-03):** `lint_tenant_settings.py` no longer exempts `apps/*/management/` for `SiteSettings.get_solo()`. Commands under tenant app prefixes (`apps/finance/`, `apps/reports/`, …) are linted like product code. New commands must use `get_platform_site_settings_record` / `get_effective_site_settings`. |

## Test and script paths (excluded from tenant-app lint)

Tests and scripts are excluded from the CI deny-list; they may call `get_solo()` for fixtures and setup. No new production tenant-facing code may call `get_solo()` without being added to the allowlist and this doc.

## Adding a new allowlisted path

1. Add the path to `ALLOWED_GET_SOLO_PREFIXES` in `scripts/lint_tenant_settings.py` (should be rare; default is **only** `models.py` + `helpers.py`).
2. Add a row to the table above with the path and reason.
3. Prefer migrating the call to `get_effective_site_settings(request)` or `get_platform_site_settings_record` instead of expanding the allowlist.

## 9.5/10 minimum enforcement

- **Runtime as law:** No new tenant-facing behavior may be driven by direct `SiteSettings` or `get_solo()` reads. New code must use runtime resolvers and precedence (see `docs/architecture/RESOLUTION_CHAIN.md`). CI enforces via `scripts/lint_tenant_settings.py --check-get-solo-only` in `scripts/pre_deploy_gate.sh`; any new allowlist entry must be justified and documented here.
- **Path to 10:** Migrate remaining allowlisted call sites to `get_effective_site_settings(request)` or resolver layer; shrink allowlist over time. To list allowlisted get_solo() usages (migration backlog), run: `python scripts/lint_tenant_settings.py --report-allowlisted --base .`
- **Allowlist shrink (BACKLOG §2e row 11):** **Done:** `get_solo()` lint allowlist is **only** `siteconfig/models.py` + `platform_runtime/helpers.py`. Management commands under tenant app trees (`apps/finance/`, `apps/reports/`, …) must use `get_platform_site_settings_record` / `get_effective_site_settings`, not `SiteSettings.get_solo()`. `backfill_runtime_defaults` uses `get_platform_site_settings_record(create=True)` and passes that into `RuntimeDefaults.sync_from_site_settings(site_settings)`.

## References

- `docs/architecture/SITESETTINGS_AUDIT.md`
- `docs/architecture/RESOLUTION_CHAIN.md`
- `docs/PLATFORM_TRANSITION_AUDIT_REPORT.md`
- `apps/platform_runtime/helpers.py` (canonical helpers)
