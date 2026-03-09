# Full deployment guide (Part A B9)

Single reference for production deploy: Render blueprint, SSL, CDN, RLS, health, and go-live. For day-to-day Render usage see [DEPLOY_RENDER.md](./DEPLOY_RENDER.md); for env and pre-merge checks see [DEPLOY_CHECKLIST.md](./DEPLOY_CHECKLIST.md).

---

## 1. render.yaml summary

**Services:**

| Service | Type | Purpose |
|--------|------|--------|
| `school-management-system` | web | Django app (Gunicorn). Serves all HTTP; health check at `/health/`. |
| `school-management-system-worker` | worker | Celery worker (tasks, offline sync, etc.). |
| `school-management-system-beat` | worker | Celery beat (scheduled tasks). |
| `school-management-redis` | redis | Cache, Celery broker, sessions. |
| `school-management-db` | postgres | Primary database (schema-per-tenant when `USE_DJANGO_TENANTS=1`). |

**Web service:**

- **buildCommand:** `./build.sh`
- **preDeployCommand:** `./scripts/release/render_predeploy.sh` — runs migrations (shared + tenant when django-tenants), seeds, optional integration preflight, optional `seed_render_users` when `ADMIN_PASSWORD` is set.
- **startCommand:** `bash ./scripts/release/render_start_web.sh` — Gunicorn bound to `0.0.0.0:$PORT`.
- **healthCheckPath:** `/health/` (public health endpoint).

**Key env vars (set in Blueprint or Dashboard):**

- `DATABASE_URL` — from Postgres internal URL (required for persistence).
- `REDIS_URL` / `CELERY_BROKER_URL` — from Redis service.
- `SECRET_KEY` — required in production (Blueprint can generate).
- `DEBUG=0` — in production.
- `USE_DJANGO_TENANTS` — `1` for schema-per-tenant (default with Postgres), `0` for shared table + RLS.
- `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` — include base domain and `*.yourdomain.com` for tenants.
- `MULTI_TENANT_BASE_DOMAIN`, `SESSION_COOKIE_DOMAIN`, `CSRF_COOKIE_DOMAIN` — for subdomain tenants.
- `ADMIN_PASSWORD` — optional; enables `seed_render_users` in predeploy.
- `RUN_INTEGRATION_PREFLIGHT=1` — recommended; fails deploy if enabled integrations lack credentials.

---

## 2. Wildcard SSL

For tenant subdomains (e.g. `*.runmycampus.com`):

- **Render:** Use a [custom domain](https://render.com/docs/custom-domains) and add a wildcard CNAME (e.g. `*.runmycampus.com` → your web service). Render provides SSL for the domain.
- **Let's Encrypt (self-hosted):** DNS-01 challenge: `certbot certonly --manual -d "*.yourdomain.com" -d yourdomain.com`. Configure your reverse proxy (Caddy/Nginx) to use the cert path.
- **Caddy:** Handles issuance/renewal; put `*.yourdomain.com` in Caddyfile.
- **Cloudflare / CDN:** Terminate SSL at the proxy; use their wildcard or per-hostname certs.

See [DEPLOYMENT_SSL_CDN.md](./DEPLOYMENT_SSL_CDN.md) for more detail.

---

## 3. CDN

- **Cache-control:** Set `Cache-Control` and `Vary` on static/asset views (e.g. long `max-age` for hashed assets). See [DEPLOY_CHECKLIST.md](./DEPLOY_CHECKLIST.md) “CDN / edge”.
- **Asset versioning:** Use `STATIC_URL` with `?v=` or hashed filenames so CDN/browsers cache by version.
- **Recommended:** Put a CDN (Cloudflare, Render CDN, or Nginx) in front of the app; origin to app URL; optional static-only subdomain. See [DEPLOYMENT_SSL_CDN.md](./DEPLOYMENT_SSL_CDN.md).

---

## 4. RLS / tenant isolation

- **Schema-per-tenant (`USE_DJANGO_TENANTS=1`):** Each tenant has its own PostgreSQL schema. Isolation is by schema; no RLS needed inside tenant schema. Shared tables (e.g. `Client`, `Domain`) live in `public`.
- **RLS mode (`USE_DJANGO_TENANTS=0`):** Single schema; tenant = school; row-level security and `app.current_school_id` scope tenant data. Ensure RLS policies are applied and verified.

**Verification:**

- Run `python manage.py db_health_check` (or equivalent) to confirm tenant isolation (e.g. schema A cannot see schema B).
- See [docs/architecture/tenancy.md](./architecture/tenancy.md) for where tenant is set and how schema/RLS is used.

---

## 5. Health endpoints

| Endpoint | Purpose | Used by |
|----------|---------|--------|
| `/health/` | Public health (no auth). Returns `{"status": "healthy"}`. | Render `healthCheckPath`, load balancers, uptime checks. |
| `/healthz/` | Internal health (can include DB). | Optional internal/API-key checks. |
| `/ready/` | Same health behavior as `/health/` on all hosts. | Optional readiness probes. |
| `/status/` | **Tenant/manager:** same as `/health/`. **Public (apex):** marketing trust page (not health). | On apex use `/health/` or `/healthz/` for health; do not use `/status/` for health on the public host. |
| `/api/health/` | API health (e.g. JSON). | API consumers. |

**Note:** On the **public (apex)** host, `/status/` is the **marketing trust/uptime page**; `/uptime/` is an alias. For health checks on the apex host use **`/health/`** or **`/healthz/`** (e.g. Render `healthCheckPath: /health/`).

Predeploy does **not** call health; it runs migrations and seeds. Ensure the app starts and `/health/` returns 200 after deploy.

---

## 6. Go-live checklist

Use this order for a new environment or major release:

1. **Migrations:** Run `python manage.py migrate --noinput` (single-schema) or `migrate_schemas --shared` then `migrate_schemas --tenant` (django-tenants). Predeploy script does this on Render.
2. **Static:** `python manage.py collectstatic --noinput`.
3. **Deploy check:** `python manage.py check --deploy`.
4. **Env:** Confirm `DATABASE_URL`, `SECRET_KEY`, `DEBUG=0`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and tenant-related vars.
5. **Health:** After start, `GET /health/` returns 200.
6. **Smoke test:** Login, one tenant subdomain, backend and portal load.
7. **DNS / custom domain:** Point base and `*.yourdomain.com` to the web service.
8. **SSL:** Wildcard or per-hostname cert in place (Render or proxy).
9. **Backup / rollback:** Confirm backup job; document rollback (e.g. redeploy previous commit, DB restore if needed).

For pre-merge and phase checks see [DEPLOY_CHECKLIST.md](./DEPLOY_CHECKLIST.md) “Pre-merge checklist”. For release steps (tag → post-release) see [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md).
