# Optional: Bridge / schema sharding for phased rollout

Part 0 optional. Group tenant schemas into clusters (e.g. by region) so migrations or deploys can be applied to one cluster at a time (e.g. update Europe while Asia is asleep).

## Concept

- **Bridge** (or migration cluster): A grouping of `Client` records (tenant schemas). Example: `europe`, `americas`, `asia`, `default`.
- **Use case:** Run `migrate_schemas --tenant` only for Clients in a given cluster; schedule clusters in separate maintenance windows to reduce blast radius and timezone-friendly rollout.

## Implementation options

1. **Add field to Client (django-tenants)**  
   Add `migration_cluster` or `region` (CharField) to the `Client` model (in your tenant app, e.g. schools). When running migrations, filter:  
   `Client.objects.filter(migration_cluster='europe')` then run migrations per schema for that subset.

2. **Separate mapping table (public schema)**  
   Table `schema_cluster` with `schema_name` (or `client_id`) and `cluster`. Join to Client when building the list of schemas for a given cluster.

3. **Use existing RegionConfig / country**  
   If each School (or Domain) has a country/region, derive cluster from that (e.g. country in EU → cluster `europe`). No new model; compute cluster in a management command from School.default_region or Domain.

## Management command

Extend or add a command, e.g.:

- `python manage.py migrate_tenant_schemas_one_by_one --cluster europe`  
  Only run tenant migrations for Clients (or Schools) in cluster `europe`. Same per-tenant failure isolation as `migrate_tenant_schemas_one_by_one`; see [MIGRATION_RUNNER_TENANT_SCHEMAS.md](MIGRATION_RUNNER_TENANT_SCHEMAS.md).

## Status

- **Not implemented.** Primary migration path remains: `migrate_schemas --shared` then `migrate_schemas --tenant` for all tenants. Use this doc when you need phased rollout by region/cluster.
