# SiteSettings.get_solo() — Allowlist

**Purpose:** Tenant-facing code must not call `SiteSettings.get_solo()` for tenant behavior; use `request.tenant_runtime` or `apps.platform_runtime.helpers` (e.g. `get_effective_site_settings(request)`). This document lists every production file where `get_solo()` is **allowed** and the reason. CI enforces zero `get_solo()` in tenant apps (see `scripts/lint_tenant_settings.py --check-get-solo-only`).

## Allowlisted production paths

| Path | Reason |
|------|--------|
| `apps/siteconfig/models.py` | Definition and internal use of singleton (e.g. `get_solo()` method, default helpers). |
| `apps/platform_runtime/helpers.py` | Canonical shim layer; uses `get_solo()` as platform fallback for `get_effective_site_settings`, `get_effective_flags`, `get_site_display_name`. |
| *(removed)* | ~~apps/policies/resolver.py~~ — **1.3 done:** Resolver uses `get_effective_site_settings(school=)` only; no get_solo(). |
| `apps/siteconfig/management/commands/*` | Control-plane / ops only (seed, export, bootstrap). |
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

## References

- `docs/architecture/SITESETTINGS_AUDIT.md`
- `docs/architecture/RESOLUTION_CHAIN.md`
- `docs/PLATFORM_TRANSITION_AUDIT_REPORT.md`
- `apps/platform_runtime/helpers.py` (canonical helpers)
