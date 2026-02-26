# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Gilead School Management System — a multi-tenant Django 5.x SaaS platform for schools (Cameroon/Africa focus). Single Django project with ~21 apps under `apps/`, plus `emis/` and `payment/`.

### Tech stack

- **Python 3.12.3**, **Django 5.x**, SQLite (dev) / PostgreSQL (prod)
- **Admin theme:** django-unfold
- **Key deps:** WeasyPrint (PDF), Celery (optional), Redis (optional), DRF + SimpleJWT

### Running the dev server

```bash
python3 manage.py runserver 0.0.0.0:8000
```

The app uses multi-tenant routing. The default tenant is `gilead-school`, so URLs look like:
- Login: `http://localhost:8000/t/gilead-school/authentication/login/`
- Backend dashboard: `http://localhost:8000/t/gilead-school/authentication/backend/`
- Django admin: `http://localhost:8000/admin/`

### Default accounts

| Username | Password     | Role         |
|----------|-------------|--------------|
| admin    | Sch00l_1234 | SUPERADMIN   |
| teacher  | Test1234    | TEACHER      |
| parent   | Test1234    | PARENT       |

The admin password from the data migration is `admin`, but `ensure_superuser --password Sch00l_1234` resets it. After a fresh `migrate`, run `ensure_superuser --password Sch00l_1234 --no-input` to set the known password.

### Database

Dev uses SQLite at `db_working.sqlite3`. No PostgreSQL or Redis needed for local development. The `.env` file (copied from `.env.local`) sets `DB_FILE=db_working.sqlite3`.

### Running tests

```bash
python3 manage.py test apps.<app_name>.tests --verbosity=2 --no-input
```

There are 115+ test files across the apps. Tests use in-memory SQLite.

### System checks (linting)

No flake8/ruff/pyproject.toml configured. Use Django's built-in checks:

```bash
python3 manage.py check
```

### Gotchas

- The `.env.local` file has a Windows-style `DB_FILE=%TEMP%\gilead_db.sqlite3`. On Linux, override `DB_FILE=db_working.sqlite3` in `.env`.
- The data migration `0021_ensure_default_admin_user.py` sets admin password to `admin`. Run `ensure_superuser` after migrate to set a known password.
- `collectstatic` reports duplicate static file warnings for admin JS files — this is harmless (django-unfold overrides).
- WeasyPrint requires system libraries (libpango, libcairo, libgdk-pixbuf) which are pre-installed in the Cloud VM.
- Celery and Redis are optional; the app runs fine without them for development.
- `python-json-logger` v4.x changed its API; if you see import warnings, they are non-blocking.
- One pre-existing test failure in `test_admin_requires_login` — the redirect URL differs due to multi-tenant routing.
