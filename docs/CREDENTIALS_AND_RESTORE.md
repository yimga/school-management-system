# Why credentials disappear and how to restore them

## Why users and data disappear

- **On Render (or any host with ephemeral disk):** If you do not set `DATABASE_URL` to a PostgreSQL database, the app uses SQLite on the server disk. That disk is ephemeral and is wiped on every deploy or restart, so all users and data are lost.
- **Locally:** If you switch DB_FILE, use a new database, or run against an empty/corrupted DB, you will have no users until you recreate them.

## Fix on Render: use PostgreSQL and preDeployCommand

1. **Blueprint (render.yaml):** The repo uses a Blueprint with database `school-management-db`. `DATABASE_URL` is set from that database. **You must set `ADMIN_PASSWORD`** in Render Dashboard → Web Service → Environment (e.g. Sch00l_1234).
2. **preDeployCommand** in render.yaml runs: `migrate --noinput` then `seed_render_users`. That creates or updates **admin**, **teacher1**, and **Parent1** using `ADMIN_PASSWORD`.
3. If you are not using the Blueprint: create a PostgreSQL database, add `DATABASE_URL` and `ADMIN_PASSWORD` to the Web Service Environment, and set **Release Command** (or preDeployCommand) to:
   ```
   python manage.py migrate --noinput && python manage.py seed_render_users
   ```
4. Redeploy. After each deploy, admin, teacher1, and Parent1 will be created or updated.

**Full list of usernames and config:** see [CONFIG_AND_USERNAMES_REFERENCE.md](CONFIG_AND_USERNAMES_REFERENCE.md).

## Restore credentials locally

```bash
python manage.py migrate --noinput
python manage.py ensure_superuser --no-input --password Sch00l_1234
python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --password Sch00l_1234
```

## Add credentials to an existing database

If you **already have a DB** (e.g. `db_working.sqlite3` or a Postgres DB) and only need to (re)create admin, teacher1, and Parent1 **without** creating a new database or wiping data:

1. Ensure your app is using that DB (e.g. `DB_FILE` in `.env.local` for SQLite, or `DATABASE_URL` for Postgres).
2. From the project root run:

```bash
python manage.py ensure_superuser --username admin --password Sch00l_1234 --no-input
python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --password Sch00l_1234
```

- **admin** is created or updated (and promoted to superuser if it already existed).
- **teacher1** and **Parent1** are created or updated with the given password.
- **Nongni.Novi** and any other custom users are not created by these commands; add them in Django Admin after logging in as admin: **/admin/** → Accounts → Users → Add.

## Standard seed accounts (Render / create_teacher_parent_accounts)

| Username   | Password (example) | Role     |
|------------|---------------------|----------|
| admin      | ADMIN_PASSWORD or admin123 (DEBUG) | Superuser |
| teacher1   | Same as ADMIN_PASSWORD when using seed_render_users | Teacher  |
| Parent1    | Same as ADMIN_PASSWORD when using seed_render_users | Parent   |

Exact usernames are **admin**, **teacher1**, **Parent1** (case-sensitive). See [CONFIG_AND_USERNAMES_REFERENCE.md](CONFIG_AND_USERNAMES_REFERENCE.md) for Buea seed usernames (teacher_buea_01, parent_buea_001, etc.).

## Other users (e.g. Nongni.Novi)

No built-in seed for custom usernames. Recreate them in Django Admin (/admin/) after logging in as admin: Accounts, Users, Add user. Or restore from a database backup.

## Full local reset (fresh SQLite)

```bash
python scripts/create_fresh_db_and_accounts.py
```

Then set DB_FILE=db_clean.sqlite3 in .env.local and start the server. Creates admin (admin123 in DEBUG), teacher, and parent (Test1234).
