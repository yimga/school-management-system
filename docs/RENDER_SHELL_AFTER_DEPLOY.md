# Render Shell — Commands to Run After Deployment

After a deploy completes, you can run these in the **Render Dashboard → your web service → Shell** for optional verification. Pre-deploy already runs migrations, health check, collectstatic, and seed steps; these are **post-deploy checks only**.

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

## Summary: minimal post-deploy check

If you only run one thing in Render Shell after deploy:

```bash
python manage.py check && python manage.py db_health_check
```

Both should succeed. For more assurance, add `python manage.py synthetic_probe --db --ready` and, with tenants, `python manage.py check_tenant_runtime`.
