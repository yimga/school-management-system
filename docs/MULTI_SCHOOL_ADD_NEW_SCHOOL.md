# Adding a New School (Option A: Same Server, Separate Database)

This guide enables an admin or DevOps person to add a **new school** to the platform on the **same server** with a **separate database** and config—**without changing application code**. Each school has its own URL, database, Site Settings, and region, and is fully isolated from other schools.

**Audience:** Technical staff (sysadmin, platform owner) with server access who can run commands, edit config, and configure DNS/reverse proxy.

---

## Prerequisites

- Server with the SMS codebase deployed (or deployment package)
- Python environment and dependencies installed (same as for an existing school)
- **Subdomain routing:** Ability to create DNS records (e.g. `school2.yourdomain.com`) and to configure the web server (e.g. Nginx)
- **Path-based routing:** Ability to configure the web server and (if using one process) a database router or env-based DB selection
- **Decision:** Use **one process per school** (recommended) with its own env file and DB, or **one process with multiple DBs** and a router keyed by subdomain/path. This KB covers both; Option 5a (separate process per school) is simpler and recommended.

---

## Step 1: Create the new database

### SQLite

- Create a new file, e.g. `db_school_slug.sqlite3`, in a dedicated directory (e.g. `data/school_slug/`).
- Ensure the directory exists and the process user has read/write access.
- Use a stable **school slug** (e.g. `buea-primary`, `douala-high`) for the file or directory name; you will use it in env and routing.

Example:

```bash
mkdir -p /var/sms/data/school_slug
touch /var/sms/data/school_slug/db.sqlite3
chown sms:sms /var/sms/data/school_slug/db.sqlite3
```

Full path to document: `DATA_DIR/school_slug/db.sqlite3` (e.g. `/var/sms/data/school_slug/db.sqlite3`).

### PostgreSQL

- Create a new database and user, e.g. `createdb school_slug`, and grant the app user access.
- Document the connection string (e.g. `postgres://sms_user:xxx@localhost:5432/school_slug`) and ensure SSL/network access is configured as required.

Example:

```bash
sudo -u postgres createuser sms_school2 --pwprompt
sudo -u postgres createdb -O sms_school2 school_slug
```

Connection string: `DATABASE_URL=postgres://sms_school2:YOUR_PASSWORD@localhost:5432/school_slug`.

---

## Step 2: Environment configuration for the new school

- Create a **dedicated env file** for this school (e.g. `.env.school_slug` or `envs/school_slug.env`). Do **not** overwrite the existing school’s env.
- One process per school should read **only** this env file.

**Required variables (with examples):**

| Variable | Purpose | Example (SQLite) | Example (PostgreSQL) |
|----------|---------|------------------|----------------------|
| `DATABASE_URL` | Postgres connection | (leave unset for SQLite) | `postgres://sms_user:xxx@localhost:5432/school_slug` |
| `DB_FILE` | SQLite path | `DB_FILE=/var/sms/data/school_slug/db.sqlite3` | (leave unset) |
| `REGION_CODE` | ISO region: currency, grading, date format | `REGION_CODE=CMR` (Buea) or `NGA`, `USA`, etc. | same |
| `TIME_ZONE` | IANA timezone for “today” and reports | `TIME_ZONE=Africa/Douala` | same |
| `LANGUAGE_CODE` | Default UI language | `LANGUAGE_CODE=en` or `fr` | same |
| `SECRET_KEY` | **Must be unique per school** (do not share) | Generate: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` | same |
| `ALLOWED_HOSTS` | Host(s) for this school | `school2.yourdomain.com` or `yourdomain.com` if path-based | same |

**Optional (per school if needed):** `DEBUG`, `SENTRY_DSN`, `EMAIL_*`, `CACHE_*`, `CELERY_*`.

**No other application code change** is required; only this env file (and process/server config) differ.

---

## Step 3: Run migrations and seed reference data

1. **Activate** the env for this school, e.g.:
   ```bash
   set -a
   source .env.school_slug
   set +a
   ```
   Or use a process manager that loads that env.

2. Run migrations so the new DB has all tables:
   ```bash
   python manage.py migrate
   ```

3. **Region reference data:** If the project has a `seed_regions` (or similar) management command, run it so RegionConfig and GradingScaleConfig exist. If not, the default region (CMR/Cameroon) is created on first use via `RegionConfig.get_default()`; add other regions (e.g. USA, NGA) via Django admin → Site config → Region Configurations.

4. **Optional:** Load initial data (e.g. academic year, terms) via fixtures or management commands if the project provides them.

5. **SiteSettings:** The first request or admin login will typically create the singleton (`get_or_create` pk=1). After first login, the admin must go to **Site Settings** and set school name, logo, region, timezone, and feature flags.

---

## Step 4: Create the first admin user for the new school

- With the **new school’s env** active, run:
  ```bash
  python manage.py createsuperuser
  ```
  Or use an existing management command (e.g. `ensure_superuser`) if the project has one.

- Store username/password securely; **do not reuse** other schools’ credentials.
- This user exists **only** in this school’s database; there is no cross-school login.

---

## Step 5: Configure the web application process

### Option 5a – Separate process per school (recommended)

- Run one Gunicorn/uWSGI (or equivalent) process **per school**, each with its own env file.
- Example:
  ```bash
  gunicorn config.wsgi:application --bind 127.0.0.1:8002 --env-file .env.school2
  ```
- Document the **port or socket** for each school so the reverse proxy can route to it (e.g. school1 → 8001, school2 → 8002).

### Option 5b – Single process with database router

- If using **one process** and **multiple DBs**, the router must select the DB (e.g. from subdomain in middleware setting `connection`/router, or from an env set per request).
- Add middleware or a DB router that maps subdomain (or path) → `db_alias` and ensure every request uses the correct DB. This is more advanced; **Option 5a is simpler and recommended.**

---

## Step 6: Configure the reverse proxy (e.g. Nginx)

### Subdomain-based routing

- Add a `server` block (or `server_name`) for the new school’s host, e.g. `school2.yourdomain.com`.
- Proxy pass to the **correct backend** (e.g. `http://127.0.0.1:8002` for school2).
- Configure SSL (e.g. Let’s Encrypt) for that host.

Example (minimal):

```nginx
server {
    server_name school2.yourdomain.com;
    location / {
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Path-based routing (optional)

- If using a path (e.g. `/school/school2/`), document how the proxy strips or forwards the path and which backend (or which env) is selected.
- Include any middleware that sets the DB or env from the path.

**Reminder:** Add the new host to **ALLOWED_HOSTS** in the school’s env (Step 2).

---

## Step 7: Initial setup in the admin (post-first-login)

1. Log in to the **new school’s** admin using the URL for that school and the superuser created in Step 4.

2. **Site Settings:** Set site name, tagline, logo, primary/accent colors, timezone, and any feature flags. Set **region** (or rely on `REGION_CODE` in env as the default).

3. **Region:** If the school is in a different country, ensure the correct RegionConfig exists (from `seed_regions`) and that the school’s env uses that region code (e.g. `REGION_CODE=NGA` for Nigeria).

4. **Academic year / terms:** Create the first academic year and terms for this school (or import them if the project provides an import).

5. **Optional:** Create the first teacher, classroom, and student for testing.

---

## Step 8: Verification checklist

- [ ] New school URL loads (subdomain or path) and shows the login page.
- [ ] Login with the new school’s superuser succeeds; **no cross-school data** is visible.
- [ ] Site Settings shows the new school’s name and logo after configuration.
- [ ] Creating an academic year, term, or test student works and is stored **only** in the new DB.
- [ ] Reports and finance use the **correct region** (currency, date format) for this school.
- [ ] **Existing school(s)** still work; no regression on their URLs.

---

## Step 9: Backup, monitoring, and maintenance

- **Backups** must be **per-database**. For example:
  - SQLite: back up `db_school_slug.sqlite3` (or `data/school_slug/db.sqlite3`).
  - PostgreSQL: back up the database `school_slug` (e.g. `pg_dump school_slug > backup_school_slug.sql`).
- **Restore:** Restore into the same (or a new) DB file/database and point the school’s env at it.
- **Logs and monitoring:** Use per-process or per-DB logging so that issues for one school do not get lost in a single log stream.
- **Add another school:** Repeat Steps 1–8 with a new slug and new env file.

---

## Option B (same DB multi-tenant) – future

When **Option B** is implemented (School model, tenant FK, school-scoped config), a **separate KB** will describe how to add a new school by creating a new **School** row and (if applicable) running a “bootstrap school” command. That KB will **not** create a new database; it will add a new tenant in the same DB and configure subdomain → school resolution.

---

## Summary

| Step | Action |
|------|--------|
| 1 | Create new DB (SQLite file or Postgres database) with a stable school slug |
| 2 | Create dedicated env file with DATABASE_URL/DB_FILE, REGION_CODE, TIME_ZONE, SECRET_KEY, ALLOWED_HOSTS |
| 3 | Activate env, run `migrate`, optionally `seed_regions` |
| 4 | Run `createsuperuser` (or equivalent) for the new school |
| 5 | Run one app process per school (recommended) with that school’s env |
| 6 | Configure Nginx (or other proxy) to route the school’s host to that process |
| 7 | Log in to the new school’s admin and set Site Settings, academic year/terms |
| 8 | Verify isolation and region behaviour |
| 9 | Set up per-DB backups and per-process/per-DB monitoring |

No application code changes are required for Option A; only deployment and configuration.
