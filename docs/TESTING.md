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

## Django check

Always safe to run; no tests, no DB writes:

```bash
python manage.py check
```
