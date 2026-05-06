# Live Render parity report

**Generated:** 2026-05-06T07:18:00-04:00

**Repo fix commit pushed:** `942ea069f930cd1d2cff5e63370afb83a435e827`

**Verdict:** `LIVE PARITY PARTIAL`

## Deployed Commit

The deployed commit SHA is still unverified. The repo-side fix commit `942ea069f930cd1d2cff5e63370afb83a435e827` was pushed to `origin/main`, but current live `/-/version/` does not yet expose JSON commit metadata after polling:

- `https://school-management-system-2kzk.onrender.com/-/version/` -> 200 `text/html`
- `https://manager.runmycampus.com/-/version/` -> 302 `/`
- `https://runmycampus.com/-/version/` -> 200 `text/html`

Repo-side closure was added for the next deploy:

- `/-/version/` registered on root, public, and manager URLConfs
- payload allowlist: `commit_sha`, `build_time`, `app_version`, `environment`
- invalid or missing commit reports `unknown`
- no environment dump or secret keys

## Public Smoke

Official public domain:

- `https://runmycampus.com/` now resolves from this certifier host.
- Apex DNS returns A records `216.24.57.7` and `216.24.57.251`.
- Apex homepage returned 200.
- Apex route smoke: `/resources/product-tour/` -> 200, `/book-demo/` -> 302 `/demo/`, `/pricing-packages/` -> 200, `/solutions/` -> 200, `/resources/` -> 200.
- `HEAD /trust/` returned 405 with `Allow: GET`; this is not classified as a page failure without a GET browser smoke.

Manager domain DNS:

- `manager.runmycampus.com` resolves as CNAME `school-management-system-2kzk.onrender.com`.

Direct Render service supplementary smoke:

- `https://school-management-system-2kzk.onrender.com/` -> 200
- `/product-tour/` -> 302 `/resources/product-tour/`
- `/demo/` -> 200
- `/trust/` -> 200
- `/pricing/` -> 200
- `/solutions/` -> 200
- `/resources/` -> 200

Desktop and mobile Playwright checks on the direct Render service showed the premium story, Book Demo, Product Tour, and premium CSS link. Console messages were empty.

## Offline Sync Behavior

Live unauthenticated manager behavior improved from the prior blocker:

- `https://manager.runmycampus.com/offline/sync/` -> 302 `/authentication/login/?next=/offline/sync/`

Repo-side fallback was also added so root-URLConf requests to `/offline/sync/` no longer raw 404:

- anonymous users redirect to login
- authenticated non-control-plane users receive 403
- authenticated control-plane users render Offline Sync Center
- tenant isolation and manager authenticated behavior are preserved

## Manager Smoke

Prior authenticated smoke remains recorded:

- `/super/` -> 200, title `Control Plane`
- `/offline/sync/` -> 200, title `Offline Sync Center`
- Premium CSS links visible and fetchable with session: `rmc-premium-os.css` and `rmc-premium-polish.css`
- Shell markers present: `data-rmc-os-shell`, `data-rmc-premium-shell`, primary action, action rail
- `/offline/sync/` shows tenant-scoped explanatory copy
- Playwright console messages: none

Rendered density:

| Page | Visible links | Visible buttons | Visible panels |
| --- | ---: | ---: | ---: |
| `/super/` | 27 | 22 | 6 |
| `/offline/sync/` | 21 | 22 | 5 |

## Tenant / Portal Smoke

Tenant and portal flows were not certified. No specific tenant slug/context was available for School Command Center, Teacher Workspace, Family Home, Money Center, Insights Center, App Marketplace, Payment Readiness Center, Event Timeline, or Configuration Center certification.

## Render Shell Commands

Not run. No Render shell/dashboard access was available from this environment.

## Local Tests And Verifiers

- `python manage.py test apps.platform_runtime.tests.test_live_version_endpoint --settings=config.settings --noinput --keepdb` -> 4 tests OK
- `python manage.py check --settings=config.settings` -> OK
- `python manage.py validate_marketing_urls --smoke` -> passed
- `python scripts/audit_route_surface.py` -> `ROUTE SYSTEM CERTIFIED`, `broken_count: 0`
- `python scripts/verify_test_module_contract.py` -> OK
- `python scripts/verify_doc_plan_density_discipline.py` -> PASS
- `python scripts/verify_sot_pillar_evidence.py` -> OK
- `python scripts/audit_security_surface.py` -> OK
- `python scripts/audit_tenant_isolation.py` -> OK
- `python scripts/run_kill_test.py` -> PASS

## Commit And Push

- `git commit -m "Add live parity version endpoint and offline sync fallback"` -> `942ea069f930cd1d2cff5e63370afb83a435e827`
- `git pull --rebase origin main` -> current branch up to date after stashing generated verifier-only outputs
- `git push origin main` -> pushed `e194771f..942ea069`
- `git rev-parse main` == `git rev-parse origin/main` immediately after the code-fix push

## Blockers

- Deployed commit SHA could not be verified as `942ea069f930cd1d2cff5e63370afb83a435e827` or newer until `/-/version/` is deployed and returns JSON metadata.
- Tenant/portal flows were not certified without a tenant context.
- Render shell commands were not available.
- SOT/log were not updated because the live certification bar was not met.

Full-market category-defining status remains blocked until listed external dependencies are verified live or formally scoped out.
