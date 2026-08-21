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

Two files at the **repo root** also belong to this build: `.dockerignore` (the
build context is the repo root, and Docker does not read `.gitignore` — so this
is what keeps your `.env`, `.venv` and host `node_modules` out of the image) and
`scripts/write_build_stamp.py` (see *Knowing what code a box is running*, below).

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

> The bring-up above is the **full multi-tenant stack** (schema-per-tenant,
> `.env.example`, worker+beat, real domains). For a **single school on an offline
> LAN mini-PC**, use the sovereign edge profile instead — see the next section.

## Edge / sovereign box (fresh install, ONE school, no Render data)
This is the on-prem path — a single school (e.g. Gilead Tech High) on a mini-PC
served over a plain-HTTP LAN, with no cloud dependency. It uses
[`.env.edge.example`](../deploy/selfhost/.env.edge.example), which runs in
**shared-DB + RLS mode** (`USE_DJANGO_TENANTS=0`, `SINGLE_TENANT=True`) so a bare
LAN hostname/IP resolves to the one school without per-subdomain DNS.

```bash
cd beta/school-management-system
cp deploy/selfhost/.env.edge.example deploy/selfhost/.env
$EDITOR deploy/selfhost/.env     # set SECRET_KEY, POSTGRES_PASSWORD, ALLOWED_HOSTS (LAN host/IP)
docker compose -f deploy/selfhost/docker-compose.yml up -d --build
```

Boot applies migrations only — **an empty DB has no school and no login.** Create
+ entitle Gilead in **one idempotent, self-verifying command**:

```bash
docker compose -f deploy/selfhost/docker-compose.yml exec web \
  python manage.py provision_sovereign_school --create \
    --email owner@school.lan --password "<StrongPass>"
```

This runs the real `create_school` engine (creates the `gilead-tech` school +
a loginable owner and **proves `authenticate()` succeeds before returning**),
then binds the `sovereign-self-hosted` plan + every feature and enables offline
mode. Re-running is safe. Then verify the box:

```bash
docker compose -f deploy/selfhost/docker-compose.yml exec web \
  python manage.py check_edge_readiness --strict
```

> ⚠ **Do NOT use `seed_render_users` on the edge box.** It is Render-shaped: at
> `DEBUG=0` with no `ADMIN_PASSWORD` / `DEFAULT_TENANT_SLUG` / `DEFAULT_TENANT_ADMIN_PASSWORD`
> set (none are in `.env.edge.example`) it deliberately creates **nothing** — no
> superuser, no school, no login. `provision_sovereign_school --create` is the
> edge path.

**Any tenant, not just Gilead.** This self-host capability is platform-wide —
Gilead is only the showcase instance. Any other school self-hosts the same way
via the tenant-agnostic `create_school` engine directly (same create + owner +
synchronous provision + auto-applied offline; it just omits the Gilead-only
COMPLIMENTARY "unlock every feature" grant):

```bash
docker compose -f deploy/selfhost/docker-compose.yml exec web \
  python manage.py create_school \
    --name "Buea Model School" --slug buea-model --email owner@buea.lan --country CM
```

`provision_sovereign_school --create` is exactly this engine plus the
sovereign entitlement, resolved under the canonical `gilead-tech` slug.

Broker-less note: if you drop the `worker`/`beat` services, add a cron for
`python manage.py run_periodic_jobs` (the complete beat-less rail — drainers +
events outbox + daily DR snapshot). See the tail of `.env.edge.example`.

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

## Knowing what code a box is running
```bash
curl -s http://<host>:10000/-/version/
# {"commit_sha": "93a06fcb8…", "build_time": "2026-08-21T12:31:20Z",
#  "app_version": "3.2.1", "environment": "selfhost"}
```
Render sets `RENDER_GIT_COMMIT` for free, so the hosted deploy could always answer
this. A self-hosted box could not: nothing in `deploy/` ever set a commit, so
`/-/version/` returned `unknown` for all three fields and no operator — or
whoever they called for help — could tell which code the box was on. It also left
`resolve_deploy_commit_sha()` inert, and that value is what the post-deploy
cache-buster stamps into `<meta name="rmc-deploy-sha">`; while it is `unknown` a
browser has nothing to notice a stale shell by, so an upgraded box keeps serving
the old one.

The image now stamps itself. `deploy/selfhost/Dockerfile` runs
`scripts/write_build_stamp.py`, which writes `.build-stamp.json` from the `.git`
in the build context — so a plain `docker compose build` is enough and there is
nothing to remember. Building from a tarball with no `.git`, or wanting the stamp
to name a CI run instead of a working copy? Pass it:

```bash
GIT_COMMIT=$(git rev-parse HEAD) docker compose -f deploy/selfhost/docker-compose.yml build
```

At runtime the resolver prefers a deploy env var, then the stamp, then `.git`. An
env var that is **set but malformed** reports `unknown` rather than falling
through — post-deploy smoke compares this value against the commit it meant to
ship, so a confident wrong answer is worse than no answer.

`check_edge_readiness` (which `entrypoint.web.sh` runs on every boot) reports the
build identity, so a box that cannot name its own code says so in its boot log.

> **Label the box with `ENVIRONMENT`, never `DJANGO_ENV`.** `config/settings.py`
> feeds `DJANGO_ENV` into `_IS_CLOUD_DEPLOYED`, so `DJANGO_ENV=production` on an
> appliance silently flips it into hosted-cloud posture: `is_cloud_host()` turns
> true, the AI tier chain drops Ollama — the only provider an offline box has —
> and hosted conversion / paid-install enforcement switches on. The compose file
> sets `ENVIRONMENT`, which nothing routes on, and a test pins that.

## Pre-cutover checklist (do before trusting it)
- [ ] `docker compose build` succeeds (globe bundle + collectstatic).
- [ ] Migrations apply cleanly against a **copy** of prod data.
- [ ] Worker drains a test task; beat schedules fire.
- [ ] Static/media served (reverse proxy or WhiteNoise).
- [ ] Backups scheduled for the Postgres volume (`pgdata`).
- [ ] Secrets in `.env` are not committed (`.env` is gitignored; only `.env.example` is tracked).
- [ ] `/-/version/` reports a real `commit_sha` — not `unknown`. If it does not,
      the image predates the build stamp; rebuild it.
- [ ] The image does not carry your secrets: `docker run --rm --entrypoint sh
      runmycampus-selfhost:latest -c 'ls -a deploy/selfhost/ | grep -c "^\.env$"'`
      should print `0`. Docker ignores `.gitignore`, so before the repo-root
      `.dockerignore` existed, `COPY . .` baked `deploy/selfhost/.env` — with
      `SECRET_KEY`, `POSTGRES_PASSWORD` and `DJANGO_CRYPTOGRAPHY_KEY` — into the
      image layer, where it travelled with any `docker save` or registry push.
