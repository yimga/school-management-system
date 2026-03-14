# Render Shell — Commands to Run After Deployment

After a deploy completes, you can run these in the **Render Dashboard → your web service → Shell** for optional verification. Pre-deploy already runs migrations, health check, collectstatic, and seed steps; these are **post-deploy checks only**.

---

## 0. “I don’t see most changes after deploy” — run these

If the app looks unchanged after a deploy (no new marketplace/catalog data, Studio OS, marketing, or control-plane content), do the following.

**If you don't see Studio OS, marketplace, or control plane at all:**

1. **Use the manager URL, not the default Render URL.** Studio OS and `/super/` (control plane, marketplace) are **only** on the manager host: **https://manager.&lt;your-base-domain&gt;** (e.g. **https://manager.runmycampus.com**). The default Render URL (e.g. `xxx.onrender.com`) is the public/marketing host and does not serve `/super/` or `/studio/`. See **§0b** for the full table.
2. **Set up the manager host:** In Render, add a custom domain **manager.runmycampus.com** (or `manager.&lt;your-base-domain&gt;`) pointing to your web service; set **MULTI_TENANT_BASE_DOMAIN** and add **manager.runmycampus.com** to **ALLOWED_HOSTS**. Then log in as superuser and open **https://manager.runmycampus.com/super/** and **https://manager.runmycampus.com/studio/**.
3. **Seed and clear cache:** Run the Shell commands in **B** below (`bootstrap_platform_catalog --all`, then cache clear). Optional: set **RUN_BOOTSTRAP_PLATFORM_CATALOG=1** in Render env so future deploys seed automatically.

**One-line Shell (after deploy):** `python manage.py check && python manage.py bootstrap_platform_catalog --all && python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"`

### A. Confirm deploy and pre-deploy ran

1. **Render Dashboard** → your **Web** service → **Deployments**.
2. Open the latest deploy; ensure **Build** and **Pre-Deploy** both finished successfully.
3. **Pre-Deploy Command** must be: `./scripts/release/render_predeploy.sh` (see `render.yaml`). If it’s missing or different, set it and **Manual Deploy** → **Clear build cache & deploy**.
4. If the deploy used an old commit, run **Manual Deploy** → **Deploy latest commit**.

### B. Run these in Render Shell (after deploy)

Open **Dashboard → Web service → Shell** and run in order:

```bash
# 1. Sanity
python manage.py check
```

```bash
# 2. Seed platform catalog (marketplace, blueprints, workflows, dashboards, registries)
#    Without this, App catalog / Blueprint marketplace / control-plane catalogs stay empty.
python manage.py bootstrap_platform_catalog --all
```

```bash
# 3. Optional: business glossary for metadata catalog
python manage.py seed_business_glossary
```

```bash
# 4. Clear cache so UI shows new data (stale dashboard/config otherwise)
python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"
```

```bash
# 5. Optional: DB health
python manage.py db_health_check
```

### C. Make future deploys seed automatically (optional)

In **Render Dashboard** → **Web** service → **Environment**:

- Add: **RUN_BOOTSTRAP_PLATFORM_CATALOG** = `1`

Then **Manual Deploy** → **Deploy latest commit**. Pre-deploy will run `bootstrap_platform_catalog --all` on every deploy so you don’t need to run it in Shell. To only seed blueprints + marketplace (faster), add **RUN_MINIMAL_BOOTSTRAP** = `1` as well.

---

## 0b. Where you see Studio OS, marketplace, and control plane

The app uses **two kinds of hosts**. You must use the right URL for each.

### Manager (control plane) — super-admin / platform ops

Use the **manager** host. With `MULTI_TENANT_BASE_DOMAIN=runmycampus.com` that is:

**https://manager.runmycampus.com**

(Replace `runmycampus.com` with your actual base domain if different.)

| What | URL (on manager host) |
|------|------------------------|
| **Control plane dashboard** | `/super/` |
| **Studio OS** (shell + Experience, Automation, Output, Launch, Control) | `/studio/` or `/studio/experience/` |
| **Blueprint marketplace** | `/super/marketplace/blueprints/` |
| **App catalog** | `/super/marketplace/apps/` |
| **Marketplace governance** | `/super/marketplace/` |
| **Runtime inspector** | `/super/runtime-inspector/` |
| **Command center** | `/super/command-center/` |
| **Create school / Launch Studio** | `/super/create/` |
| **Billing** | `/super/billing/` |

**Important:** The default Render URL (e.g. `school-management-system-2kzk.onrender.com`) is treated as the **public** host (marketing + login). It does **not** serve `/super/` or `/studio/`. To use the manager surfaces you must:

1. Add a **custom domain** in Render: **manager.runmycampus.com** (or `manager.<your-base-domain>`) pointing to your web service.
2. Add that host to **ALLOWED_HOSTS** in Render env (e.g. `manager.runmycampus.com`).
3. Log in with a **superuser** (or user with control-plane access), then open **https://manager.runmycampus.com/super/** and **https://manager.runmycampus.com/studio/**.

### School (tenant) — per-school backend and Studio

Use a **school subdomain** (or the school’s custom domain). Example with base domain `runmycampus.com`:

**https://&lt;school-slug&gt;.runmycampus.com**

| What | URL (on school host) |
|------|------------------------|
| **Backend dashboard** | `/backend/` |
| **Studio OS** (for that school) | `/studio/` or `/studio/experience/` |
| **App catalog** (tenant) | `/settings/app-catalog/` |

Log in with a user that has access to that school, then open `/backend/` and `/studio/`.

### Local development

- **Manager:** **http://manager.localhost:8000/super/** and **http://manager.localhost:8000/studio/**
- **Tenant:** **http://&lt;slug&gt;.localhost:8000/backend/** and **http://&lt;slug&gt;.localhost:8000/studio/**

---

## 1. Quick sanity check (recommended)

```bash
python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

For stricter production checks:
```bash
python manage.py check --deploy
```

---

## 2. DB and readiness (optional)

```bash
python manage.py db_health_check
```
Expected: `db_health_check OK`

```bash
python manage.py synthetic_probe --db --ready
```
Expected: `synthetic_probe: all checks OK` (process + DB + ready URL).

---

## 3. Tenant / schema verification (optional)

Only when **USE_DJANGO_TENANTS=1**:

```bash
python manage.py check_tenant_runtime
```
Verifies tenant schema setup and that runtime is consistent.

```bash
python manage.py verify_tenant_rls
```
Verifies RLS policies on tenant tables (if RLS is enabled).

---

## 4. Region / catalog (optional, first deploy or after adding countries)

```bash
python manage.py seed_global_regions
python manage.py verify_region_coverage
```
Use `verify_region_coverage --strict` in CI to fail if any country is missing.

---

## 5. Cache clear (only if you see stale UI after deploy)

In Render Shell:
```bash
python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"
```

---

## What you should **not** run in Shell after deploy

- **Do not** run `python manage.py migrate` when `USE_DJANGO_TENANTS=1`. Migrations are done in **pre-deploy** via `migrate_schemas --shared` and `migrate_schemas --tenant`. Running plain `migrate` can break tenant schemas.
- **Do not** run `collectstatic` manually for a normal deploy; pre-deploy already runs it.
- **Do not** run `migrate_schemas` again unless you are intentionally re-running tenant migrations (e.g. after fixing a failed migration); pre-deploy already does it once.

---

## 6. Platform 9.5 / Master Checklist (optional)

To confirm packages/setup_studio migrations are applied and optionally seed the business glossary (so metadata catalog shows glossary entries):

```bash
python manage.py showmigrations packages setup_studio
python manage.py seed_business_glossary
```

---

## Summary: minimal post-deploy check

If you only run one thing in Render Shell after deploy:

```bash
python manage.py check && python manage.py db_health_check
```

Both should succeed. For more assurance, add `python manage.py showmigrations packages setup_studio`, `python manage.py synthetic_probe --db --ready`, and, with tenants, `python manage.py check_tenant_runtime`. See **`docs/MASTER_PLATFORM_CHECKLIST.md`** section "Render: verify after deploy" for the canonical list.
