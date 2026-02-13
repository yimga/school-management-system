# Why credentials disappear and how to restore them

## Why users and data disappear

- **On Render (or any host with ephemeral disk):** If you do not set `DATABASE_URL` to a PostgreSQL database, the app uses SQLite on the server disk. That disk is ephemeral and is wiped on every deploy or restart, so all users and data are lost.
- **Locally:** If you switch DB_FILE, use a new database, or run against an empty/corrupted DB, you will have no users until you recreate them.

## Fix on Render: use PostgreSQL and preDeployCommand

Checklist (all required):

1. **PostgreSQL:** Create a Postgres database in Render and copy its Internal Database URL.
2. **Environment variables (Web Service -> Environment):**
   - `DATABASE_URL` = full Internal Database URL.
   - `ADMIN_PASSWORD` = password for seeded users (for example `Sch00l_1234`).
3. **Deploy command:** Use `./scripts/release/render_predeploy.sh` as preDeployCommand (Blueprint) or Release Command.
4. **Redeploy and verify logs:** This runs migrations plus seed/update for `admin`, `teacher1`, `Parent1`, and `principal1`.

If you are not using Blueprint setup, use this fallback Release Command:

```bash
python manage.py migrate --noinput && python manage.py ensure_superuser --no-input --password $ADMIN_PASSWORD && python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --principal-username principal1 --password $ADMIN_PASSWORD
```

If users still cannot log in, confirm the deploy logs show the release/predeploy step completed without errors.

Full list of usernames and config: [CONFIG_AND_USERNAMES_REFERENCE.md](CONFIG_AND_USERNAMES_REFERENCE.md).

## Admin account does not work again (Render or local)

On Render:

1. Verify `ADMIN_PASSWORD` is set in Web Service -> Environment.
2. Verify preDeployCommand or Release Command is configured correctly.
3. Redeploy and check logs for superuser/seed output.
4. Log in at `/authentication/login/` with username `admin` and password from `ADMIN_PASSWORD`.

Locally (reset admin password):

```bash
python manage.py ensure_superuser --username admin --password Sch00l_1234 --no-input
```

Then log in at `/authentication/login/` or `/admin/`.

## Restore credentials locally

```bash
python manage.py migrate --noinput
python manage.py ensure_superuser --no-input --password Sch00l_1234
python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --principal-username principal1 --password Sch00l_1234
```

## Add credentials to an existing database

If you already have a DB (for example `db_working.sqlite3` or Postgres) and only need to recreate admin/teacher/parent/principal users without wiping data:

1. Ensure the app points to that DB (`DB_FILE` in `.env.local` for SQLite, or `DATABASE_URL` for Postgres).
2. Run:

```bash
python manage.py ensure_superuser --username admin --password Sch00l_1234 --no-input
python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --principal-username principal1 --password Sch00l_1234
```

- `admin` is created or updated (and promoted to superuser if it already existed).
- `teacher1`, `Parent1`, and `principal1` are created or updated.
- Custom users are not created by these commands; add them in Django admin (`/admin/`).

## Standard seed accounts (Render / create_teacher_parent_accounts)

| Username   | Password (example) | Role |
|------------|---------------------|------|
| admin      | `ADMIN_PASSWORD` or `Sch00l_1234` in DEBUG | Superuser |
| teacher1   | Same as `ADMIN_PASSWORD` when using `seed_render_users` | Teacher |
| Parent1    | Same as `ADMIN_PASSWORD` when using `seed_render_users` | Parent |
| principal1 | Same as `ADMIN_PASSWORD` when using `seed_render_users` | Principal |

Exact usernames are `admin`, `teacher1`, `Parent1`, `principal1` (case-sensitive). See [CONFIG_AND_USERNAMES_REFERENCE.md](CONFIG_AND_USERNAMES_REFERENCE.md) for Buea seed usernames (`teacher_buea_01`, `parent_buea_001`, etc.).

## Other users

No built-in seed exists for custom usernames. Recreate them in Django admin (`/admin/`) or restore from backup.

## Full local reset (fresh SQLite)

```bash
python scripts/create_fresh_db_and_accounts.py
```

Then set `DB_FILE=db_clean.sqlite3` in `.env.local` and start the server.
