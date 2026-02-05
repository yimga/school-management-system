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

## Optional env vars on Render

- `ALLOWED_HOSTS` – Only if you add a custom domain (e.g. `yourapp.com,.onrender.com`).
- `CSRF_TRUSTED_ORIGINS` – Only if you use a custom domain (e.g. `https://yourapp.com`).
- `DEBUG=0` – Recommended in production.
- `DATABASE_URL` – For PostgreSQL (recommended for production).
- `SECRET_KEY` – Required in production.
