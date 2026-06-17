# Self-host migration: Render → your own server

> **Status: BACKLOG / external (future).** The Docker Compose stack under
> [`deploy/selfhost/`](../deploy/selfhost/) is a complete, ready-to-use scaffold,
> but it has **not yet been run end-to-end against production data** — validate it
> on a staging box before cutting over. Nothing here touches the live Render
> deployment. Owner-driven; do when ready to move off Render.

## Why
The entire stack is open-source and **zero-lock-in** — PostgreSQL, Valkey (the
BSD Redis fork), Celery, Django. Self-hosting on a server you already own means
**$0 hosting fees** (just your hardware/power), full control, and no per-service
Render billing. This is the long-term cost + sovereignty play.

## What's in `deploy/selfhost/`
| File | Role |
|---|---|
| `Dockerfile` | One image (Python 3.12 + Node globe bundle + collectstatic), reused by web/worker/beat. Mirrors `build.sh`. |
| `docker-compose.yml` | Full topology: `web` + `worker` + `beat` + `db` (Postgres 16) + `valkey`. |
| `entrypoint.web.sh` | Waits for DB, runs `migrate_schemas` (tenant-aware), starts gunicorn. |
| `.env.example` | All required env (secrets, domains, sizing, email). Copy to `.env`. |

The compose file wires `DATABASE_URL`/`REDIS_URL`/`CELERY_BROKER_URL` to the
internal services automatically. Because a `worker` runs, `CELERY_BROKER_URL` is
set (broker is opt-in + worker-safe — see `config/settings.py`).

## Bring-up (on the target server)
```bash
cd beta/school-management-system
cp deploy/selfhost/.env.example deploy/selfhost/.env
$EDITOR deploy/selfhost/.env                       # set SECRET_KEY, POSTGRES_PASSWORD, domains
docker compose -f deploy/selfhost/docker-compose.yml up -d --build
# First run applies migrations automatically. Then seed the super-admin:
docker compose -f deploy/selfhost/docker-compose.yml exec web python manage.py seed_render_users
```
Put a TLS-terminating reverse proxy (Caddy/nginx/Traefik — all open-source) in
front of `web:10000` for HTTPS + the apex/wildcard tenant domains.

## Migrating the data from Render
1. **Dump** the Render Postgres: `pg_dump "$RENDER_DATABASE_URL" -Fc -f rmc.dump`
   (or use Render's backup download).
2. **Restore** into the self-host DB:
   `docker compose ... exec -T db pg_restore -U rmc -d runmycampus --no-owner < rmc.dump`
   (django-tenants schemas come across with the dump; verify with
   `manage.py detect_tenant_table_drift`).
3. Point DNS (apex + `*.` wildcard) at the new server; flip TLS.
4. Verify `https://<host>/health/` → `redis_configured: true`,
   `celery_broker_configured: true`, `database_configured: true`.

## Pre-cutover checklist (do before trusting it)
- [ ] `docker compose build` succeeds (globe bundle + collectstatic).
- [ ] Migrations apply cleanly against a **copy** of prod data.
- [ ] Worker drains a test task; beat schedules fire.
- [ ] Static/media served (reverse proxy or WhiteNoise).
- [ ] Backups scheduled for the Postgres volume (`pgdata`).
- [ ] Secrets in `.env` are not committed (`.env` is gitignored; only `.env.example` is tracked).
