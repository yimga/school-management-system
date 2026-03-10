# Testing

## Quick smoke (no database)

Runs in under a second; no migrations. Use when switching gears or in CI when DB is unavailable:

```bash
python manage.py test apps.accounts.tests.test_smoke_urls --verbosity=2
```

Covers: home, health, admin, accounts, siteconfig, portal, analytics, reports, evals, finance, marketing (blog detail, book-demo, discover).

## Focused suite (with database)

Runs URL + control plane + redirect + runtime-helper tests. Requires full migrations (~2–5 min on first run):

```bash
python manage.py test apps.accounts.tests.test_smoke_urls apps.schools.tests.test_phase10_control_plane_verification apps.siteconfig.tests.test_redirect_safety apps.portal.tests.test_runtime_helpers apps.finance.tests.test_runtime_helpers --verbosity=2
```

## Full suite

Runs all tests (178+ modules). Can take 10+ minutes; use when preparing a release:

```bash
python manage.py test --verbosity=1 --parallel 4
```

To run a single app’s tests:

```bash
python manage.py test apps.siteconfig.tests --verbosity=2
python manage.py test apps.finance.tests --verbosity=2
```

High-end admin and platform styling (login template, no-tenant copy, unfold callback):

```bash
python manage.py test apps.siteconfig.tests.test_admin_high_end --verbosity=2
```

## Pre-commit (run before commit)

With your **virtualenv activated** and dependencies installed (`pip install -r requirements.txt`):

```powershell
# Windows (from repo root)
.\scripts\run_tests_pre_commit.ps1
```

Or manually:

```bash
python manage.py check
python manage.py test --verbosity=1 --parallel 4
```

## Marketing (72 non-negotiables)

Per [MARKETING_NON_NEGOTIABLES.md](MARKETING_NON_NEGOTIABLES.md), run before release or in CI:

```bash
python manage.py validate_marketing_urls
python manage.py validate_marketing_urls --smoke
```

- **validate_marketing_urls:** Django `check` + resolution of 14 marketing URL names.
- **--smoke:** GETs 6 key routes (landing, book-demo, 10-reasons, integrations, app-marketplace, developers) with `HTTP_HOST=runmycampus.com` and expects 200.

Automated tests (same coverage; require DB and migrations):

```bash
python manage.py test apps.schools.tests.test_marketing_validation -v 2
```

Covers: URL resolution for all 14 names, smoke GET 200 for 6 key URLs, landing context contains required visual keys (`migration_studio_image_url`, `platform_architecture_diagram_url`, `school_in_a_box_flow_image_url`, `data_intelligence_loop_image_url`, `product_visualization_slides`), platform and products-analytics pages have `page_extras`, onboard wizard returns 200.

## Django check

Always safe to run; no tests, no DB writes:

```bash
python manage.py check
```
