# Cache readiness plan (no new cache layer in this pass)

## Safe cache candidates (when a tenant-scoped cache utility already exists)

| Surface | Candidate keys | Invalidation risk |
| --- | --- | --- |
| Dashboard aggregates | `tenant:{school_id}:dashboard:*` | Any grade/finance write must bust related keys |
| Evidence summaries | `tenant:{id}:evidence:{slug}` | Config mutation / template publish |
| Report template catalogs | `tenant:{id}:report_templates` | Siteconfig report template edits |
| Marketplace catalog | `global:marketplace_catalog` (read-mostly) | Publisher app version changes |

## Tenant cache key requirements

- Prefix every key with tenant or school identifier from `get_tenant_cache_prefix` patterns used in portal services.
- Never cache user-specific permission decisions without including `user_id` in the key.

## Must NOT cache (initially)

- Raw HTML of authenticated pages with CSRF tokens embedded.
- Whole `SiteSettings` rows without versioning (use runtime merge + short TTL only if introduced later).

## Next step

Introduce caching only behind an existing Redis/cache helper already wired in settings; until then this document is planning-only.
