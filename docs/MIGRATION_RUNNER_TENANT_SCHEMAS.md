# Migration Runner for All Tenant Schemas

Part 0 of the RunMyCampus Single Plan. When app schema changes, migrations must be applied to **all** tenant schemas in an atomic/idempotent way. Tables created per schema = **Master Table List** ([MASTER_TABLE_LIST.md](MASTER_TABLE_LIST.md)).

## Standard approach

1. **Shared first:** `python manage.py migrate_schemas --shared --noinput`
2. **All tenants:** `python manage.py migrate_schemas --tenant --noinput`

The built-in `migrate_schemas --tenant` iterates over all `Client` records and runs migrations in each tenant schema. This is the default and is used in deploy (e.g. [scripts/release/render_predeploy.sh](../scripts/release/render_predeploy.sh)).

## Per-schema failure handling

- **Principle:** If a migration fails on **one** tenant schema, roll back **only that schema** and alert; other schemas proceed.
- **django-tenants behavior:** `migrate_schemas --tenant` runs each tenant in sequence. If one fails, the command exits and later tenants are not run. There is no built-in "skip failed and continue."
- **Recommendation:** Use the optional management command `migrate_tenant_schemas_one_by_one` (see below) to run migrations per tenant with try/except: on failure, log the error and the schema name, then continue to the next tenant. Each tenant runs in its own transaction so a failure does not roll back others.
- **Rollback of a single schema:** Migrations are applied forward only. To "roll back" a schema after a failed migration, you must either: (a) fix the migration and re-run, or (b) restore that schema from backup. Document which schema failed so ops can target it.

## Idempotency

- Running `migrate_schemas --tenant` multiple times is idempotent: already-applied migrations are recorded in `django_migrations` in each schema and are skipped.

## Optional: phased rollout (bridge / schema sharding)

- The plan mentions an optional "Bridge" model where schemas are grouped into clusters (e.g. by region) for phased rollout (e.g. update Europe while Asia is asleep). This is **not** implemented here. To add it: (1) add a `migration_cluster` or `region` field to Client (or a separate mapping), (2) run `migrate_schemas --tenant` only for Clients in a given cluster, (3) schedule clusters in separate maintenance windows.

## Management command: migrate_tenant_schemas_one_by_one

- **Command:** `python manage.py migrate_tenant_schemas_one_by_one [--dry-run]`
- **Behavior:** For each Client, run tenant migrations inside `tenant_context(client)`. On failure, log and continue to the next tenant. Does not replace `migrate_schemas --tenant`; use when you want per-tenant failure isolation and a report of which schemas failed.

See [apps/schools/management/commands/migrate_tenant_schemas_one_by_one.py](../apps/schools/management/commands/migrate_tenant_schemas_one_by_one.py).
