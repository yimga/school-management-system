# Config and URLs audit

Quick reference of what was verified. Run `python manage.py check` and the URL checks below to re-verify after changes.

---

## 1. Django system check

- **Result:** `System check identified no issues (0 silenced).`
- Re-run: `python manage.py check`

---

## 2. Settings – connections and auth

| Setting | Value | Notes |
|--------|--------|------|
| **Database** | `DATABASE_URL` → PostgreSQL; else SQLite (`db_working.sqlite3` or `DB_FILE`) | `.env.local` loaded with `override=False` so Render `DATABASE_URL` is not overwritten. |
| **LOGIN_URL** | `/authentication/login/` | Matches `accounts` namespace: `path('authentication/', include(..., 'accounts'))` + `path('login/', ...)`. |
| **LOGIN_REDIRECT_URL** | `/authentication/redirect/` | Post-login goes to `accounts:redirect` (role-based). |
| **LOGOUT_REDIRECT_URL** | `/authentication/login/` | |
| **AUTH_USER_MODEL** | `accounts.User` | |
| **ALLOWED_HOSTS** | From env; `.onrender.com` appended when `RENDER=true`. | |
| **CSRF_TRUSTED_ORIGINS** | From `CSRF_TRUSTED_ORIGINS` or `RENDER_EXTERNAL_HOSTNAME` (https://...) | |
| **SECURE_PROXY_SSL_HEADER** | `('HTTP_X_FORWARDED_PROTO', 'https')` | For Render/HTTPS. |

---

## 3. Root URL routing (`config/urls.py`)

| Path | Namespace / view | Purpose |
|------|------------------|--------|
| `/` | `home` → redirect to `accounts:redirect` or `accounts:login` | Entry. |
| `/admin/` | Django admin (Unfold) | |
| `/authentication/` | `accounts` | Login, logout, redirect, profile, backend, workflow, certification, MFA. |
| `/backend/` | Redirect to `accounts:backend_dashboard` | |
| `/portal/`, `/portal` | `portal` (no trailing slash redirects to `portal:parent_dashboard`) | Parent/teacher portal. |
| `/evals/` | `evals` | Evals/teacher dashboard. |
| `/reports/` | `reports` | |
| `/finance/` | `finance` | |
| `/analytics/` | `analytics` | |
| `/payroll/` | `payroll` | |
| `/compliance/` | `compliance` | |
| `/communication/` | `communication` | |
| `/requests/` | `requests` | |
| `/siteconfig/` | `siteconfig` | |
| `/api/` | `api` + root-level `api/schema/`, `api/schema/ui/` | REST + schema. |
| `/kb/` | `kb` (portal KB) | |
| `/emis/` | `emis` | |
| `/health/`, `/healthz/`, `/metrics/` | Observability | |

---

## 4. URL name resolution (verified)

These names resolve correctly:

- `accounts:login` → `/authentication/login/`
- `accounts:redirect` → `/authentication/redirect/`
- `accounts:backend_dashboard` → `/authentication/backend/`
- `accounts:user_profile` → `/authentication/profile/`
- `portal:parent_dashboard` → `/portal/parent/`
- `portal:parent_finance` → `/portal/parent/finance/`
- `portal:parent_performance` → `/portal/parent/performance/`
- `evals:teacher_dashboard` → `/evals/teacher/`
- `home` → `/`
- `api-schema` → `/api/schema/`

---

## 5. Permissions and login redirect

- `apps.accounts.permissions`: `redirect_url="/authentication/login/"` — matches `LOGIN_URL`.
- Views use `reverse("accounts:login")` or `redirect(reverse("accounts:redirect"))` as appropriate.

---

## 6. Render (`render.yaml`)

- **buildCommand:** `./build.sh`
- **startCommand:** `.venv/bin/gunicorn config.wsgi:application`
- **envVars:** DEBUG, PYTHON_VERSION, ALLOWED_HOSTS, SECRET_KEY. **DATABASE_URL** must be set in Dashboard (not in YAML so it is not overwritten).
- **databases:** `school-management-db` (optional link).

---

## 7. WSGI

- `config.wsgi:application` — uses `config.settings` via `DJANGO_SETTINGS_MODULE`.

---

**Re-verify URLs (optional):**

```bash
python manage.py shell -c "
from django.urls import reverse
for n in ['accounts:login', 'accounts:redirect', 'portal:parent_dashboard', 'home']:
    print(n, '->', reverse(n))
"
```

All connections and URLs checked above are consistent; no changes required for correctness.
