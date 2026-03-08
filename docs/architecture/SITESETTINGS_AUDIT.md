# SiteSettings and Runtime Bypass Audit (Phase 5)

**Rule:** No tenant behavior from `SiteSettings.get_solo()` or direct `School.settings`/`School.features`; all such behavior should go through `request.tenant_runtime` or helpers in `apps/platform_runtime/helpers.py`.

## Helpers (use these instead)

- `get_tenant_runtime(request)` — request.tenant_runtime or None
- `get_effective_branding(request)` — runtime.branding or platform fallback
- `get_effective_dashboard(request, role=..., user=...)` — runtime.dashboards / dashboard_for
- `get_effective_policy(request, module_name=...)` — runtime.policy (optional module section)
- `get_effective_locale(request)` — runtime.locale
- `get_effective_workflow(request, workflow_code)` — runtime.workflows / workflow_for

## Refactored (runtime-first)

| Location | Change |
|----------|--------|
| `apps/dashboard/context.py` | `build_dashboard_extras`: site_id and backend_flags from `request.tenant_runtime` when present |
| `config/tenant_urls.py` | `api_schema_ui`: flags from `request.tenant_runtime.flags` when present |

## Allowed (platform/control-plane)

- Control plane views (super/) that need global site name or marketing config.
- Background tasks that call `build_tenant_runtime_for_tenant(school, mode="job")` then use runtime; or platform-wide defaults.

## Remaining (to refactor in follow-up)

All other `SiteSettings.get_solo()` usages listed in codebase grep: accounts, finance, people, portal, evals, api, schools, reports, observability, automation, payroll, etc. Prefer runtime or helpers when in a tenant request context.

## CI

Avoid adding new tenant-behavior reads from `SiteSettings.get_solo()` or `School.settings`/`School.features` in tenant-facing apps; add a comment in this file when introducing an exception.
