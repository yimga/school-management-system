# Deploying on Render.com

For a full map of dashboards and links, see [DASHBOARDS_AND_LINKS.md](./DASHBOARDS_AND_LINKS.md).

## Host and CSRF (required for login to work)

- **ALLOWED_HOSTS:** When `RENDER=true` (set by Render), the app automatically allows `*.onrender.com`. You do not need to set `ALLOWED_HOSTS` in the Render dashboard unless you use a custom domain.
- **CSRF / HTTPS:** The app sets `SECURE_PROXY_SSL_HEADER` and builds `CSRF_TRUSTED_ORIGINS` from `RENDER_EXTERNAL_HOSTNAME` (set by Render). Login POST and all forms work over HTTPS. If you use a custom domain, set `CSRF_TRUSTED_ORIGINS=https://your-domain.com` in Render environment.

## Main URLs (after deploy)

| Purpose        | URL (replace `YOUR-SERVICE` with your Render host) |
|----------------|----------------------------------------------------|
| **Landing / Login** | `https://YOUR-SERVICE.onrender.com/` → redirects to login |
| **Login page**     | `https://YOUR-SERVICE.onrender.com/authentication/login/` |
| **Parent portal**  | `https://YOUR-SERVICE.onrender.com/portal/parent/` |
| **Teacher (portal)** | `https://YOUR-SERVICE.onrender.com/portal/teacher/` |
| **Teacher (evals)**  | `https://YOUR-SERVICE.onrender.com/evals/teacher/` |
| **Frontend admin dashboard** | `https://YOUR-SERVICE.onrender.com/backend` → redirects to `/authentication/backend/` |
| **Django admin**    | `https://YOUR-SERVICE.onrender.com/admin/` |

Example for `school-management-system-2kzk.onrender.com`:

- Login: https://school-management-system-2kzk.onrender.com/authentication/login/
- Parent: https://school-management-system-2kzk.onrender.com/portal/parent/
- Teacher: https://school-management-system-2kzk.onrender.com/evals/teacher/
- Frontend admin: https://school-management-system-2kzk.onrender.com/backend
- Backend admin: https://school-management-system-2kzk.onrender.com/admin/

## Database and credentials (important)

If you do **not** set `DATABASE_URL`, the app uses SQLite on the server disk. Render’s disk is **ephemeral**: it is wiped on every deploy, so **all users and data disappear** after each deploy.

- **Use PostgreSQL:** In Render, create a PostgreSQL database and set `DATABASE_URL` to its Internal Database URL in your Web Service environment. Alternatively, if your host injects separate vars, the app can build the URL from `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` when `DATABASE_URL` is not set (see `.env.example`).
- **Recreate users on each deploy:** Set a **Release Command** so admin and demo accounts exist after every deploy. See [CREDENTIALS_AND_RESTORE.md](./CREDENTIALS_AND_RESTORE.md) for the exact steps and release command (migrate + ensure_superuser + create_teacher_parent_accounts for admin, teacher1, Parent1).

## Optional env vars on Render

- `ALLOWED_HOSTS` – Only if you add a custom domain (e.g. `yourapp.com,.onrender.com`).
- `CSRF_TRUSTED_ORIGINS` – Only if you use a custom domain (e.g. `https://yourapp.com`).
- `DEBUG=0` – Recommended in production.
- `DATABASE_URL` – **Recommended.** PostgreSQL Internal Database URL so data and users persist across deploys.
- `ADMIN_PASSWORD` – Password for the `admin` account created by the release command.
- `SECRET_KEY` – Required in production.
