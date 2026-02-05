# Main Branch Health — Code & Testing Environment

Single reference to confirm **everything on main is in order** and where the **testing environment** lives in the codebase.

---

## 1. Code on main

- **Django:** `python manage.py check` passes (no system check issues).
- **URLs & links:** Hardcoded paths have been replaced with `{% url ... %}` where applicable; see **docs/DASHBOARD_AND_SITE_SETTINGS_LINKS.md** for the full link reference.
- **Admin:** Custom login page, sidebar layout fallback when static files fail, and Unfold icon overrides (SVG instead of Material Symbols text) so production does not show "dock_to_right", "manage_search", etc.
- **Backend:** Customize layout and Add widget are wired; backend student list uses `region_format` (no 500 on `/backend/students/`).
- **Static files:** Build runs `collectstatic --noinput` (see **build.sh**). Ensure production serves `STATIC_ROOT` (e.g. WhiteNoise) so CSS/fonts load.

---

## 2. Testing environment (all in the code)

### Test user creation

| Command | Purpose |
|--------|--------|
| `python manage.py ensure_superuser --no-input --password <pwd>` | Create/update superuser (admin). |
| `python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --password <pwd>` | Create teacher1 and Parent1. |
| `python manage.py seed_render_users` | For Render: creates/updates admin, teacher1, Parent1 using `ADMIN_PASSWORD`. Run after migrate in Release Command. |
| `python manage.py seed_buea_synthetic --scale small` | Full local test data (Buea); run after ensure_superuser. |

**Locations:**

- `apps/accounts/management/commands/ensure_superuser.py`
- `apps/accounts/management/commands/create_teacher_parent_accounts.py`
- `apps/accounts/management/commands/seed_render_users.py`
- `apps/academics/management/commands/seed_buea_synthetic.py`

### Environment and config

- **.env.example** — Template for `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL`, `ADMIN_PASSWORD`, feature flags, etc. Copy to `.env` or `.env.local` (never commit real secrets).
- **config/settings.py** — Loads `.env` and `.env.local`; uses `RENDER`, `DATABASE_URL`, `ADMIN_PASSWORD` for production.

### Documentation (in repo)

| Doc | Contents |
|-----|----------|
| **TESTING_AND_TEST_USERS.md** | Portals, URLs, how to create test users (local + Render), quick verification checklist. |
| **docs/CREDENTIALS_AND_RESTORE.md** | Why credentials disappear (ephemeral DB, new DB), restore on Render and locally. |
| **docs/CONFIG_AND_USERNAMES_REFERENCE.md** | Usernames and config for Render and Buea seed. |
| **docs/DASHBOARD_AND_SITE_SETTINGS_LINKS.md** | Every dashboard/sidebar and Site Settings link (URL names). |
| **TESTING_VALIDATION_GUIDE.md** | Broader testing and validation. |
| **docs/TESTING_CHECKLIST_ONBOARDING.md** | Onboarding testing checklist. |

---

## 3. Quick “everything good” checklist

- [ ] On main: `git status` shows no unintended modified/untracked code (DB backups like `db.sqlite3.corrupted` can stay untracked).
- [ ] `python manage.py check` passes.
- [ ] Local: `.env` or `.env.local` present (from `.env.example`); `migrate` and one of the user-creation commands above run successfully.
- [ ] Production: `DATABASE_URL` (Postgres) and `ADMIN_PASSWORD` set; Release Command runs `migrate --noinput && seed_render_users`; `collectstatic` runs in build and static files are served.
- [ ] After deploy: Login at `/authentication/login/`, open `/admin/`, `/authentication/backend/`, `/portal/parent/`, `/portal/teacher/` per **TESTING_AND_TEST_USERS.md** §3.

---

## 4. Optional: run tests

### Smoke test (no database)

```bash
python manage.py test apps.accounts.tests.test_smoke_urls
```

Uses **SimpleTestCase** (no DB created). Validates that critical URL names resolve correctly (home, admin, siteconfig, portal, analytics, reports, evals, finance, health). Safe for CI when the DB is missing or broken.

### Full test suite

```bash
python manage.py test
```

Requires a **healthy database** (e.g. new SQLite or Postgres). If you see "database disk image is malformed", use a fresh DB (e.g. set `DB_FILE=db_test.sqlite3` and run `migrate` then `test`).

---

**Summary:** All environments and steps needed to test the site are in the code and docs on main. Use **TESTING_AND_TEST_USERS.md** and **docs/CREDENTIALS_AND_RESTORE.md** as the main entry points for test users and deployment.
