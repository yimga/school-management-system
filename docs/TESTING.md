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

## Django check

Always safe to run; no tests, no DB writes:

```bash
python manage.py check
```
