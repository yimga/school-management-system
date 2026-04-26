# Environment variables (reference)

Values are read in `config/settings.py` and related modules. This list is **representative**; default behavior may apply when a variable is unset (read the source for the exact branch).

## Core

| Variable | Role |
|----------|------|
| `SECRET_KEY` | Django signing. **Required** when `DEBUG=0` (improperly configured otherwise). |
| `DEBUG` | `1` = dev-style errors; `0` = production. On Render, blueprint sets `0`. |
| `ALLOWED_HOSTS` | Comma-separated hosts; multi-tenant base and subdomains are appended in settings. |
| `DATABASE_URL` | **Production:** PostgreSQL via `dj_database_url` when set. If unset, settings fall back to **SQLite** for local dev (not for staging/production). `DB_HOST`+`DB_NAME`+`DB_USER`+`DB_PASSWORD`+`DB_PORT` can be composed into a URL (see `config/settings.py`). |
| `RENDER` | When `true`, `*.onrender.com` may be added to `ALLOWED_HOSTS`. |
| `RENDER_EXTERNAL_HOSTNAME` | If set and `CSRF_TRUSTED_ORIGINS` empty, one trusted origin is derived. |
| `CSRF_TRUSTED_ORIGINS` | Comma list of `https://...` origins. Settings also add `https://` + `MULTI_TENANT_BASE_DOMAIN` and wildcards for subdomains. |

## Multi-tenant

| Variable | Role |
|----------|------|
| `MULTI_TENANT_BASE_DOMAIN` | Canonical domain (default `runmycampus.com` in settings). |
| `MULTI_TENANT_LEGACY_BASE_DOMAINS` | Optional comma list for legacy host redirects. |
| `USE_DJANGO_TENANTS` | Schema-per-tenant mode; **changes migration and predeploy** (see `render.yaml`). |
| `MANAGER_PLATFORM_BASE_URL` | Deep links to manager host. |
| `STUDIO_APPROVAL_HUB_TENANT_BASE_URL` | Optional Studio approval hub base. |

## Session / cookies (example from blueprint)

| Variable | Role |
|----------|------|
| `SESSION_COOKIE_DOMAIN` | e.g. `.runmycampus.com` for cross-subdomain sessions when intended. |
| `CSRF_COOKIE_DOMAIN` | Same family as session when using shared parent domain. |

## Background / async

| Variable | Role |
|----------|------|
| `REDIS_URL` | Used when Celery/channels are enabled. |
| `CELERY_BROKER_URL` | Often same as Redis on Render. |

## Email (optional in dev)

| Variable | Role |
|----------|------|
| `EMAIL_BACKEND` | e.g. SMTP backend in production. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS` | SMTP settings. |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | **Secrets** in dashboard, not in repo. |
| `DEFAULT_FROM_EMAIL` | Envelope and display defaults. |

## Observability (optional)

| Variable | Role |
|----------|------|
| `RUM_INGEST_KEY` | If set, RUM script may load (see settings comment). |

## Static / media (see `config/settings.py`)

| Item | Default / role |
|------|----------------|
| `STATIC_URL` | `/static/`; **`collectstatic` runs in `build.sh`** (writes to `STATIC_ROOT`). |
| `STATIC_ROOT` | `staticfiles/` (project root); not overridden by env. |
| `STATICFILES_STORAGE` | `whitenoise.storage.CompressedManifestStaticFilesStorage` (WhiteNoise in middleware). |
| `MEDIA_URL` / `MEDIA_ROOT` | `/media/` and `media/`; ensure upload volume or object storage in production if you rely on user uploads. |

## HTTPS / production hardening (see `render.yaml` web service)

| Variable | Role |
|----------|------|
| `SECURE_SSL_REDIRECT` | When `1`, redirects HTTP→HTTPS in Django (set in production blueprint). |
| `PORT` | Gunicorn bind port; **Render sets this**; `render_start_web.sh` defaults to `10000` locally. |

## Runtime (web process)

| Variable | Role |
|----------|------|
| `GUNICORN_APP_MODULE` | Optional override; default `config.wsgi:application` per `scripts/release/render_start_web.sh`. |
| `RUN_STARTUP_SCHEMA_CHECK` | When not `0`, `render_start_web.sh` runs `manage.py check_tenant_runtime` before Gunicorn. |
| `DJANGO_SETTINGS_MODULE` | Should be `config.settings` (worker/beat set this explicitly in `render.yaml`; web relies on WSGI loading settings). |

## How to verify locally

- Use `.env` / `.env.local` (see `load_dotenv` in `config/settings.py`).
- Never commit real secrets. Use the same **names** as production to avoid surprises.

## Related

- `PRODUCTION_DEPLOYMENT_CHECKLIST.md` — order of operations.
- `LAUNCH_SMOKE_TEST.md`, `RELEASE_NOTES_LAUNCH.md`, `DEPLOYMENT_ROLLBACK.md` — launch bundle.
- `../RENDER_AFTER_MASTER_CHECKLIST_DEPLOY.md` (if present in repo) — project-specific follow-ups.
