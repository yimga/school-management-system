# Fix: "DATABASE_URL is not set on Render"

If pre-deploy fails with:

```text
ImproperlyConfigured: DATABASE_URL is not set on Render. Link the PostgreSQL database...
```

the web service has no `DATABASE_URL` in its environment. Fix it from the Render Dashboard.

---

## Option A: Link the database (Blueprint / same group)

1. Open **Dashboard** → **school-management-system** (your web service).
2. Go to **Environment**.
3. Check if **DATABASE_URL** is listed. If it is missing:
   - Click **Add Environment Variable**.
   - Choose **Add from Render** (or **Link to Database**).
   - Select the PostgreSQL database (e.g. **school-management-db**).
   - Pick the **Internal Database URL** (or the field that provides the connection string).
   - Save. The key should be **DATABASE_URL**.
4. **Redeploy** the web service (Deploy → Deploy latest commit, or trigger a new deploy).

---

## Option B: Set DATABASE_URL manually

1. Open **Dashboard** → your **PostgreSQL** database (e.g. **school-management-db**).
2. In **Connections**, copy the **Internal Database URL** (use Internal, not External, for a service on Render).
3. Open **Dashboard** → **school-management-system** (web service) → **Environment**.
4. Add:
   - **Key:** `DATABASE_URL`
   - **Value:** paste the Internal Database URL.
5. Save and **redeploy** the web service.

---

## Pre-Deploy Command

If you see a different pre-deploy command in the logs (e.g. `ensure_superuser` and `create_teacher_parent_accounts` instead of `seed_render_users`), the Dashboard may be overriding `render.yaml`.

- Either: In **Settings** → **Build & Deploy**, clear any custom **Pre-Deploy Command** so the Blueprint command from `render.yaml` is used:
  - ` .venv/bin/python manage.py migrate --noinput && .venv/bin/python manage.py seed_render_users`
- Or: Set Pre-Deploy Command to that same line.

Also set **ADMIN_PASSWORD** in Environment (secret) so `seed_render_users` can create **admin**, **teacher1**, and **Parent1**.
