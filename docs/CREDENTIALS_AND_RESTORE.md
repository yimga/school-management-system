# Why credentials disappear and how to restore them

## Why users and data disappear

- **On Render (or any host with ephemeral disk):** If you do not set `DATABASE_URL` to a PostgreSQL database, the app uses SQLite on the server disk. That disk is ephemeral and is wiped on every deploy or restart, so all users and data are lost.
- **Locally:** If you switch DB_FILE, use a new database, or run against an empty/corrupted DB, you will have no users until you recreate them.

## Fix on Render: use PostgreSQL and preDeployCommand

Checklist (all required):

1. **PostgreSQL:** Create a Postgres database in Render and copy its Internal Database URL.
2. **Environment variables (Web Service -> Environment):**
   - `DATABASE_URL` = full Internal Database URL.
   - `ADMIN_PASSWORD` = optional; password for **tenant demo users only** (teacher1, Parent1, principal1). Not used for the platform admin.
3. **Deploy command:** Use `./scripts/release/render_predeploy.sh` as preDeployCommand (Blueprint) or Release Command.
4. **Redeploy and verify logs:** This runs migrations plus `seed_render_users`, which always ensures platform admin `admin`/`admin` and optionally creates teacher1, Parent1, principal1 when `ADMIN_PASSWORD` is set.

If you are not using Blueprint setup, use this fallback Release Command:

```bash
python manage.py migrate --noinput && python manage.py seed_render_users
```

(Platform admin will be admin/admin; set `ADMIN_PASSWORD` if you want tenant demo users created with that password.)

If users still cannot log in, confirm the deploy logs show the release/predeploy step completed without errors.

Full list of usernames and config: [CONFIG_AND_USERNAMES_REFERENCE.md](CONFIG_AND_USERNAMES_REFERENCE.md).

## Admin account does not work again (Render or local)

On Render:

1. Predeploy always runs `seed_render_users`, which ensures platform admin **admin** / **admin**. No env var required for platform login.
2. Verify preDeployCommand or Release Command is configured correctly (e.g. `./scripts/release/render_predeploy.sh`).
3. Redeploy and check logs for seed_render_users output.
4. Log in at `/authentication/login/` or `/super/` with username **admin** and password **admin**.

Locally (reset admin password):

```bash
python manage.py ensure_superuser --username admin --password admin --no-input
```

Then log in at `/authentication/login/` or `/admin/` with **admin** / **admin**.

## Restore credentials locally

```bash
python manage.py migrate --noinput
python manage.py seed_render_users
```

This ensures platform admin **admin** / **admin**. To also create tenant demo users with a specific password:

```bash
ADMIN_PASSWORD=YourTenantPassword python manage.py seed_render_users
```

Or run the commands separately:

```bash
python manage.py ensure_superuser --username admin --password admin --no-input
python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --principal-username principal1 --password YourTenantPassword
```

## Add credentials to an existing database

If you already have a DB and only need to recreate admin/teacher/parent/principal users without wiping data:

1. Ensure the app points to that DB (`DB_FILE` in `.env.local` for SQLite, or `DATABASE_URL` for Postgres).
2. Run:

```bash
python manage.py ensure_superuser --username admin --password admin --no-input
python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --principal-username principal1 --password YourTenantPassword
```

- `admin` is created or updated with password **admin** (platform super-admin).
- `teacher1`, `Parent1`, and `principal1` are created or updated with the password you pass (tenant demo users; separate from admin).
- Custom users are not created by these commands; add them in Django admin (`/admin/`).

## Standard seed accounts (Render / seed_render_users)

Platform and tenant credentials are separate. Admin is always admin/admin; tenant demo users use ADMIN_PASSWORD when set.

| Username   | Password | Role |
|------------|----------|------|
| admin      | **admin** (fixed) | Superuser (platform) |
| teacher1   | `ADMIN_PASSWORD` when set on Render | Teacher |
| Parent1    | `ADMIN_PASSWORD` when set on Render | Parent |
| principal1 | `ADMIN_PASSWORD` when set on Render | Principal |

Exact usernames are `admin`, `teacher1`, `Parent1`, `principal1` (case-sensitive). See [CONFIG_AND_USERNAMES_REFERENCE.md](CONFIG_AND_USERNAMES_REFERENCE.md) for Buea seed usernames (`teacher_buea_01`, `parent_buea_001`, etc.).

## Other users

No built-in seed exists for custom usernames. Recreate them in Django admin (`/admin/`) or restore from backup.

## Full local reset (fresh SQLite)

```bash
python scripts/create_fresh_db_and_accounts.py
```

Then set `DB_FILE=db_clean.sqlite3` in `.env.local` and start the server.
