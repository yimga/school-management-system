# RunMyCampus deployment guide (Render)

This document aligns the **RunMyCampus Deployment Blueprint** with the existing **Django** stack on Render. The app remains Python/Django (no Next.js); the same experience and operational goals apply.

**See also:** [DEPLOY_CHECKLIST.md](../DEPLOY_CHECKLIST.md) for pre-deploy verification.

---

## 1. Infrastructure stack (render.yaml)

### render.yaml summary (B9)

| Component | Name | Plan | Notes |
|-----------|------|------|--------|
| Web | school-management-system | free | buildCommand: ./build.sh; preDeployCommand: ./scripts/release/render_predeploy.sh; startCommand: render_start_web.sh; healthCheckPath: /health/ |
| Worker | school-management-system-worker | free | Celery worker, concurrency 2 |
| Beat | school-management-system-beat | free | Celery beat, DatabaseScheduler |
| Redis | school-management-redis | free | Sessions + CELERY_BROKER_URL |
| DB | school-management-db | free | PostgreSQL |

Key env vars (web): DATABASE_URL, SECRET_KEY, REDIS_URL, CELERY_BROKER_URL, RUN_INTEGRATION_PREFLIGHT=1, APPLY_UI_FIXTURE_ON_DEPLOY=1, EMAIL_* for SMTP. Set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in Dashboard for real email.

**Pre-Deploy Command (required when USE_DJANGO_TENANTS=1):** In the Render Dashboard, set the web service **Pre-Deploy Command** to exactly:
```text
./scripts/release/render_predeploy.sh
```
Do **not** use `python manage.py migrate --noinput` (or similar). With schema-per-tenant, migrations must run as `migrate_schemas --shared` then `migrate_schemas --tenant`; the script does that and also runs collectstatic. If you use plain `migrate`, deploys will fail with "no schema has been selected to create in".

- **Web:** Python/Django (Gunicorn via `scripts/release/render_start_web.sh`).
- **Database:** Managed PostgreSQL (`school-management-db`). For production, consider moving the DB plan from `free` to `starter` or higher (High Availability, point-in-time recovery).
- **Caching:** Redis (`school-management-redis`) for sessions and Celery broker.
- **Workers:** Celery worker + Beat for async tasks and scheduled jobs.
- **Health check:** Web service uses `healthCheckPath: /health/`. Ensure the app exposes `/health/` (or `/healthz/` if you standardise on that). Render restarts the service on repeated failure.

Optional: add a comment at the top of `render.yaml` referencing the RunMyCampus Deployment Blueprint and that Pro tier for web/DB can be enabled for higher availability (e.g. 99.9% target). Do not change plans by default without approval (cost impact).

---

## 2. Custom domains and wildcard SSL

- Point your root domain (e.g. `runmycampus.com`) to Render via CNAME (or A/AAAA as per Render docs).
- In the Render dashboard, add a **custom domain** for the web service and, if supported, a **wildcard** (e.g. `*.runmycampus.com`) so each school subdomain gets SSL automatically.
- Render supports custom domains and wildcard SSL; follow the exact steps in the Render dashboard (Settings -> Custom Domains). After DNS propagation, TLS is issued for the root and `*.runmycampus.com`.
- **Multi-tenant base domain:** Set `MULTI_TENANT_BASE_DOMAIN=runmycampus.com` so bare domain routes to the public marketing landing and subdomains to tenant backends.
- **Temporary legacy compatibility:** Set `MULTI_TENANT_LEGACY_BASE_DOMAINS=legacy.runmycampus.com` during cutover.
- **Caddy on-demand TLS (optional):** If you use Caddy in front of Render, configure the “ask” endpoint so Caddy only issues certs for known tenants:
  - `ask http://localhost:8000/api/v1/auth/check-domain/?domain={domain}` (or `/api/caddy-check/`). The app returns 200 only for verified subdomains or custom domains (see `SchoolDomain` and Caddy docs). Restrict this endpoint by IP via `CADDY_CHECK_ALLOWED_IPS` in production.

---

## 3. CDN (edge performance)

- Put **Cloudflare** (or another CDN) in front of Render: add the site, set DNS to proxy through Cloudflare, and point the root (and wildcard) to the Render URL.
- Cache static and, if desired, media (logos, wallpapers) at the edge. Optional: set `Cache-Control` headers for `/static/` and `/media/` in Django so the CDN can cache; no code change is required for a basic setup.

---

## 4. Data isolation: schema-per-tenant (primary)

- **RunMyCampus uses schema-per-tenant (django-tenants) on PostgreSQL.** Each school (tenant) has its own PostgreSQL schema. The application sets the connection `search_path` to that schema per request. **Do not set `USE_DJANGO_TENANTS=0` for production** unless explicitly required.
- **Primary isolation is by schema:** Every tenant-scoped query runs in the correct schema; do not rely on `tenant_id` or RLS for isolation. RLS is optional (defense-in-depth only) and not required for correctness.
- After running migrations, you can run the verification command for optional RLS:
  ```bash
  python manage.py verify_tenant_rls
  ```
- Document in runbooks: schema-per-tenant is the standard; migrations must run as `migrate_schemas --shared` then `migrate_schemas --tenant` (see Pre-Deploy Command above).

---

## 5. Health checks

- Render calls `healthCheckPath: /health/` (or the path you configure). The app should return a successful response (e.g. 200) when the service and DB are healthy.
- Document that Render will restart the web service on repeated health-check failure.

---

## 6. Go-live checklist

- [ ] **render.yaml:** Multi-tenant Django app with web service, PostgreSQL, Redis, Celery worker, and Beat. Health check path matches the app (e.g. `/health/`).
- [ ] **RLS:** Enabled and verified on all tenant-scoped tables (`verify_tenant_rls` run after migrations).
- [ ] **Redis:** Used for sessions and (optionally) tenant cache; `REDIS_URL` and `CELERY_BROKER_URL` set.
- [ ] **School assets:** Logos and wallpapers served via CDN (and optionally from S3/Cloudinary); document `DEFAULT_FILE_STORAGE` and media bucket if used.
- [ ] **Custom domain and wildcard SSL:** Root and `*.runmycampus.com` configured and TLS active.
- [ ] **CDN:** Cloudflare (or similar) in front of Render; static/media caching as needed.
- [ ] **Multi-tenant routing:** `MULTI_TENANT_BASE_DOMAIN` set; public URLConf for base domain (marketing, signup, discover); tenant URLConf for subdomains and path-based `/t/<slug>/`.
- [ ] **Caddy ask (if used):** `/api/v1/auth/check-domain/` or `/api/caddy-check/` reachable from Caddy; `CADDY_CHECK_ALLOWED_IPS` set in production.
- [ ] **Auto-scaling:** Document Render’s scaling options for the web service (e.g. scale to N instances under load); no code change required.

---

## 7. Region coverage (pycountry)

- **Dependency:** Region seeding and verification use **pycountry** (ISO 3166-1 country list). Install with `pip install pycountry`. Optional: `geonamescache` for extended city/timezone data. See [apps/siteconfig/global_catalog.py](../apps/siteconfig/global_catalog.py).
- **At deploy:** Run `python manage.py seed_global_regions` (and optionally `seed_global_data`) so every country has a RegionConfig. Then run `python manage.py verify_region_coverage`; use `--strict` in CI to fail if any country is missing. Province seeding is optional and documented per deployment.

---

## 8. Storage (optional)

The blueprint mentions S3/Cloudinary for assets. If not already configured, document how to set `DEFAULT_FILE_STORAGE` and the media bucket for logos and wallpapers. No change to `render.yaml` is required for storage (external service).
