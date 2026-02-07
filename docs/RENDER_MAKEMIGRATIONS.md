# Generate missing migrations on Render

Render reported:

```text
Your models in app(s): 'academics', 'communication', 'finance', 'portal' have changes
that are not yet reflected in a migration.
```

Do this **on the Render Shell** (so the app uses the real DB and can detect the diff):

## 1. Generate the migrations

In the project directory (e.g. `~/project/src`):

```bash
python manage.py makemigrations academics communication finance portal
```

Django will create new migration file(s) and print something like:

```text
Migrations for 'academics':
  apps/academics/migrations/0021_something.py
  ...
```

## 2. Get the new files into the repo

- **Option A – Copy from Render:**  
  On Render, run:
  ```bash
  cat apps/academics/migrations/0021_*.py
  ```
  (and the same for any other new files under `communication`, `finance`, `portal`).  
  Create the same files in your local repo (same paths), paste the content, then commit and push.

- **Option B – Run makemigrations locally:**  
  Fix the local DB (e.g. use a new SQLite file via `DB_FILE` in `.env.local`, or restore from backup), then run the same `makemigrations` command locally. Commit the new migration files and push.

## 3. Deploy again

After the new migrations are on the branch Render deploys from, trigger a new deploy. The Release Command (`migrate --noinput && seed_render_users`) will apply the new migrations and the warning will go away.
