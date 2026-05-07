# Live Browser UX Certification Report

- Generated: 2026-05-07T18:49:43.768Z
- Commit under test: 4d179e0f9ba1917d6c9d91e3e7321fd92d4672ed
- Environment: local dev server browser QA, not Render/custom-domain live parity.
- Verdict: LIVE BROWSER UX CERTIFIED - LOCAL

## Environment
- DB: `.django_test_dbs/browser_tenant_qa.sqlite3` (not committed).
- Tenant host: `http://xp-tenant.runmycampus.com:8022`.
- Platform host: `http://manager.runmycampus.com:8022`.
- Local security env: `SECURE_SSL_REDIRECT=0`, `CSRF_COOKIE_SECURE=0`, `SESSION_COOKIE_SECURE=0`, `SECURE_CROSS_ORIGIN_OPENER_POLICY=unsafe-none` for local HTTP QA only.
- Render/custom-domain deployment was not browser-tested.

## Auth
- Tenant login: real browser form login after GET `/authentication/login/`; POST returned redirect success and no CSRF 403.
- Platform login: real browser form login on manager host.

## Platform Operator QA
- Routes: 14/14 returned 200; clean routes 14/14.

## Tenant Admin QA
- Desktop routes: 10/10 returned 200; clean routes 10/10.
- Routes tested: /school/settings/, /school/setup/blueprints/, /school/setup/packs/, /school/setup/imports/, /school/apps/, /school/money/, /school/workflows/, /school/offline/, /school/audit/, /school/security/.

## Tenant Mobile QA
- Mobile routes: 6/6 returned 200; clean routes 6/6.

## Negative Access QA
- Anonymous manager `/configuration/`, `/super/`, `/internal-admin/` redirected to login.
- Anonymous tenant `/school/settings/` redirected to login.
- Tenant user on manager-host `/configuration/`, `/super/`, and `/configuration/blueprints/` was not granted platform access.
- Public-host no-follow checks: `/super/` and `/internal-admin/` returned 302 to manager host.

## Fixes
- Corrected tenant browser auth flow instead of disabling CSRF.
- Replaced stale DB state with a fresh migrated local browser QA DB.
- Fixed tenant imports/offline/audit/security aliases and related route regressions.
- Fixed frontend console/page-error causes in Launch Studio, passive click telemetry, React Query static shim, density CSS, sidebar collapse JS, and compliance chart JSON.

## Verifiers
- `manage_check`: PASS
- `validate_marketing_urls_smoke`: PASS
- `audit_route_surface`: PASS
- `audit_security_surface`: PASS
- `audit_tenant_isolation`: PASS
- `verify_test_module_contract`: PASS
- `verify_design_system_phase2`: PASS
- `verify_shell_surface_inventory`: PASS
- `run_northstar_audit`: PASS
- `run_kill_test`: PASS
- `verify_doc_plan_density_discipline`: PASS
- `verify_sot_pillar_evidence`: PASS
## Evidence
- Raw Playwright artifact: `docs/generated/tenant_browser_qa_recovery_raw.json`.
- Certification artifact: `docs/generated/live_browser_ux_certification_report.json`.
- Screenshot directory: `tmp/screenshots/live_browser_ux_certification_recovery/` (ignored, not tracked).

## Remaining Gaps
- Render/custom-domain parity remains pending.
- This is not a full-market category-defining claim.

## Final Verdict

LIVE BROWSER UX CERTIFIED - LOCAL
