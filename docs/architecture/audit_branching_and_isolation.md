# Audit: Tenant branching (C2) and isolation (C3)

RunMyCampus blueprint: eliminate tenant-specific branching; verify media/cache/tasks/search isolation.

## C2) Find and eliminate tenant-specific branching

**Goal:** Replace `if tenant` / `if request.tenant` / `country` / `region` / hardcoded labels with Policy Registry.

### Commands (run from repo root)

```bash
# Tenant/country/region branching (exclude tests, migrations, resolver)
rg -n "if.*tenant|request\.tenant|\.country|\.region|country_code|default_region" apps/ config/ --glob '!*migration*' --glob '!*test*' -g '!*resolver*'

# Hardcoded labels — replace with policy terminology
rg -n "Principal|Proviseur|Grade|Cahier" apps/ --glob '!*migration*' --glob '!*test*'

# Raw SQL / .extra() / cursor
rg -n "\.raw\(|\.extra\(|cursor\.execute" apps/
```

### What to do

- For each match in **business logic**: replace with `get_effective_policy(school)` or `tenant_ctx` and policy keys.
- For **labels**: use Policy Registry terminology.

---

## C3) Verify isolation (media / cache / tasks / search)

**Goal:** No cross-tenant leakage; keys/paths include tenant_id or schema_name.

### Cache

See [cache_keys.md](cache_keys.md). Tenant-scoped keys must include `tenant_id` or `schema_name`.

### Media / static

Audit: `FileField`, `ImageField`, `upload_to` — ensure paths include school_id/tenant. Patch: prefix with school_id or schema_name.

### Celery / tasks

Tasks touching tenant data must use `@tenant_task` or `schema_context(schema_name)`; pass school_id/schema_name, not raw rows.

### Search

If used: index names or query filters must be tenant-scoped (school_id in filter or index).

---

## Repo-level audit commands

```bash
rg "\.raw\(" apps/
rg "school\.settings|school\.features" apps/ -g '!*resolver*' -g '!*test*' -g '!*writer*'
```
