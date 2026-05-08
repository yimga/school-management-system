# Apple-Class UX Browser Report

Generated: 2026-05-08

Verdict: **APPLE-CLASS UX PARTIAL**

## Scope

Local browser QA covered public, platform, and tenant route classes using `http://127.0.0.1:8000`. Axe was enabled. Protected platform and tenant routes were checked as unauthenticated access/login flows, not as signed-in product screens. Render/live parity was not tested.

## Result

- Playwright route/accessibility smoke: **38 passed, 0 failed**
- Targeted Apple-class Django tests: **12 OK**
- `python manage.py check --settings=config.settings`: **OK**
- `python manage.py validate_marketing_urls --smoke`: **PASS**
- Verifier stack: **PASS**

## Accessibility Note

The first axe-enabled run exposed a real contrast issue in the public homepage product-story block. The world-class hero now forces readable ink color inside the dark marketing shell, and the rerun passed.

## Route Matrix

| Route | Desktop | Mobile | Accessibility | Remaining issue |
| --- | --- | --- | --- | --- |
| `/marketing/` | pass | pass | axe pass | None |
| `/resources/product-tour/` | pass | pass | axe pass | None |
| `/pricing/` | pass | pass | axe pass | None |
| `/trust/` | pass | pass | axe pass | None |
| `/demo/` | pass | pass | axe pass | None |
| `/super/` | auth bounded | auth bounded | auth redirect only | Authenticated product surface browser QA not run |
| `/configuration/` | auth bounded | auth bounded | auth redirect only | Authenticated product surface browser QA not run |
| `/configuration/blueprints/` | auth bounded | auth bounded | auth redirect only | Authenticated product surface browser QA not run |
| `/configuration/workflow-packs/` | auth bounded | auth bounded | auth redirect only | Authenticated product surface browser QA not run |
| `/configuration/change-requests/` | auth bounded | auth bounded | auth redirect only | Authenticated product surface browser QA not run |
| `/configuration/registries/health/` | auth bounded | auth bounded | auth redirect only | Authenticated product surface browser QA not run |
| `/school/settings/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/setup/blueprints/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/setup/packs/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/setup/imports/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/money/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/offline/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/audit/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |
| `/school/security/` | auth bounded | auth bounded | auth redirect only | Authenticated tenant browser QA not run |

## Required Follow-Up

1. Run authenticated browser QA for redesigned `/super`, `/configuration`, governed installation, tenant school, app catalog, migration, and billing pages.
2. Add drawer focus-trap tests when drawers become JavaScript-active rather than static contract components.
3. Run Render parity with deployed SHA proof before any Render-ready claim.
