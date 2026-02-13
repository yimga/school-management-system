# No-Regression Targets (Dashboard & Theme Master Plan)

Lock these URLs and areas for manual or automated checks before/after changes. Used by Phase 1 and Phase 9. Smoke tests lock resolution in `apps.accounts.tests.test_smoke_urls`.

## Key URLs (locked by smoke tests where noted)

| Target | URL path | URL name | Notes |
|--------|----------|----------|--------|
| Django Admin | `/admin/` | `admin:index` | Login, dashboard, Site Settings (theme pack catalog) |
| Admin dashboard (obs) | `/admin/dashboard/` | `admin_dashboard` | Admin overview UI |
| Backend dashboard | `/authentication/backend/` | `accounts:backend_dashboard` | Welcome block, Overview, chip row, action grid, side rail |
| Teacher dashboard | `/evals/teacher/` | `evals:teacher_dashboard` | Role-adaptive, layout |
| Parent dashboard | `/portal/parent/` | `portal:parent_dashboard` | Role-adaptive, layout |
| Login | `/authentication/login/` | `accounts:login` | Auth entry |

## Preflight (Phase 1)

- `git diff --check` — no conflict markers
- `python manage.py makemigrations --check` — no unapplied model changes
- `python manage.py test apps.accounts.tests.test_smoke_urls` — URL resolution and key routes

## Before merge (Phase 9)

- All Phase 9 QA + pre-deploy gate (migration check, template compile, contrast/theme checks, smoke tests).
