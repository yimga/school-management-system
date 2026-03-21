# Studio OS rails — control plane vs tenant URLs

All **Experience, Launch, Automation, Output, and Control** left-rail entries are built with `resolve_studio_href()` / `studio_resolve_url()` in `apps/studio_os/deep_links.py` (see `apps/studio_os/views.py` `_studio_rail_append`).

## Environment

| Variable | When needed |
|----------|-------------|
| `STUDIO_APPROVAL_HUB_TENANT_BASE_URL` | Manager (or any host where `reverse("siteconfig:…")` fails). Absolute links to tenant `siteconfig/*`, and tenant-scoped `portal/*`, `accounts/*`, `automation/outcomes`, metadata API center, etc. when `reverse` is missing. |
| `MANAGER_PLATFORM_BASE_URL` | Tenant Studio linking to `super/*` or `admin/*` (e.g. Create school, runtime inspector, billing). |

## Verification

- `apps/studio_os/tests/test_studio_rail_resolution.py` — every rail viewname is listed in `_PATHS` and resolves under the test URLconf.
- `apps/studio_os/tests/test_deep_links.py` — tenant/manager base behavior.

## Not in this pass

First-party ops modules, full SOC2 execution, N10/N16–N18/N20–N24 depth, SiteSettings decomposition, and `csrf_exempt` reduction beyond `scripts/lint_csrf_exempt_usage.py` remain program work tracked in `RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` and `docs/PROGRAM_EXECUTION_REMAINING.md`.
