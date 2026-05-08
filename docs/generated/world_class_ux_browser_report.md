# World-Class UX Browser Report

Generated: 2026-05-08

Verdict: **WORLD-CLASS UX PARTIAL**

## Scope

Local Playwright smoke covered public, platform, and tenant route classes for the world-class UX/accessibility slice. The run used `http://127.0.0.1:8000`, `SKIP_AXE=1`, and unauthenticated protected-route handling. Render/live parity was not tested.

## Result

- Playwright route smoke: **37 passed, 1 failed**
- Django UX test bundle: **19 OK**
- `python manage.py check --settings=config.settings`: **OK**
- `python manage.py validate_marketing_urls --smoke`: **PASS**
- Verifier stack: **PASS**

## Browser Blocker

`/trust/` fails mobile local browser QA. The local `runserver` request returned Django debug 404 content for `/trust/`, while Django URL resolution and the marketing smoke command both resolved `/trust/` successfully as 200. The debug 404 route listing produced `130px` horizontal overflow on the 390px mobile viewport.

This means the redesigned trust template is covered by the Django smoke path, but local browser proof is not clean enough to certify the full world-class UX slice.

## Route Matrix

| Route | Desktop | Mobile | Accessibility | Remaining issue |
| --- | --- | --- | --- | --- |
| `/marketing/` | pass | pass | axe skipped | None |
| `/resources/product-tour/` | pass | pass | axe skipped | None |
| `/pricing/` | pass | pass | axe skipped | None |
| `/trust/` | bounded | fail | axe skipped | Local runserver debug 404 / overflow |
| `/demo/` | pass | pass | axe skipped | None |
| `/super/` | auth bounded | auth bounded | auth redirect only | Authenticated browser QA not run |
| `/configuration/` | auth bounded | auth bounded | auth redirect only | Authenticated browser QA not run |
| `/configuration/blueprints/` | auth bounded | auth bounded | auth redirect only | Authenticated browser QA not run |
| `/configuration/workflow-packs/` | auth bounded | auth bounded | auth redirect only | Authenticated browser QA not run |
| `/configuration/change-requests/` | auth bounded | auth bounded | auth redirect only | Authenticated browser QA not run |
| `/configuration/registries/health/` | auth bounded | auth bounded | auth redirect only | Authenticated browser QA not run |
| `/school/settings/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/setup/blueprints/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/setup/packs/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/setup/imports/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/money/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/offline/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/audit/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/security/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |

## Required Follow-Up

1. Resolve the local `runserver` `/trust/` URLConf/host discrepancy.
2. Rerun Playwright with `SKIP_AXE=0` where axe dependencies are available.
3. Rerun authenticated platform and tenant browser QA.
4. Keep Render/live parity pending until deployed SHA and live route proof are available.
