# Why credentials disappear and how to restore them

## Why users and data disappear

- **On Render (or any host with ephemeral disk):** If you do not set `DATABASE_URL` to a PostgreSQL database, the app uses SQLite on the server disk. That disk is ephemeral and is wiped on every deploy or restart, so all users and data are lost.
- **Locally:** If you switch DB_FILE, use a new database, or run against an empty/corrupted DB, you will have no users until you recreate them.

## Fix on Render: use PostgreSQL and Release Command

1. Create a **PostgreSQL** database in the Render dashboard. Copy the **Internal Database URL**.
2. In your Web Service Environment, add:
   - `DATABASE_URL` = the Internal Database URL
   - `ADMIN_PASSWORD` = password for the admin account (e.g. Sch00l_1234)
3. In Web Service Settings, Build and Deploy, set **Release Command** to:
   ```
   python manage.py migrate --noinput && python manage.py ensure_superuser --no-input --password $ADMIN_PASSWORD && python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --password $ADMIN_PASSWORD
   ```
4. Redeploy. After each deploy, admin, teacher1, and Parent1 will be created or updated.

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

## Standard seed accounts

| Username   | Password (example) | Role     |
|------------|---------------------|----------|
| admin      | ADMIN_PASSWORD or admin123 (DEBUG) | Superuser |
| teacher1   | Set when running create_teacher_parent_accounts | Teacher  |
| Parent1    | Set when running create_teacher_parent_accounts | Parent   |

## Other users (e.g. Nongni.Novi)

No built-in seed for custom usernames. Recreate them in Django Admin (/admin/) after logging in as admin: Accounts, Users, Add user. Or restore from a database backup.

## Full local reset (fresh SQLite)

```bash
python scripts/create_fresh_db_and_accounts.py
```

Then set DB_FILE=db_clean.sqlite3 in .env.local and start the server. Creates admin (admin123 in DEBUG), teacher, and parent (Test1234).
