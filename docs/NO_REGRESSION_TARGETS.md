# No-Regression Targets (Dashboard & Theme Master Plan)

Lock these URLs and areas for manual or automated checks before/after changes. Used by Phase 1 and Phase 9.

## Key URLs

| Target | URL / path | Notes |
|--------|------------|--------|
| Django Admin | `/admin/` | Login, dashboard, Site Settings (theme pack catalog) |
| Backend dashboard | `/authentication/backend/` or app backend dashboard URL | Welcome block, Overview, chip row, action grid, side rail |
| Teacher dashboard | Teacher dashboard URL | Role-adaptive, layout |
| Parent dashboard | Parent dashboard URL | Role-adaptive, layout |

## Preflight (Phase 1)

- `git diff --check` — no conflict markers
- `python manage.py makemigrations --check` — no unapplied model changes
- `python manage.py test apps.accounts.tests.test_smoke_urls` — URL resolution and key routes

## Before merge (Phase 9)

- All Phase 9 QA + pre-deploy gate (migration check, template compile, contrast/theme checks, smoke tests).
