# DR: backups, tenant schemas, restore drills

**Purpose:** Operator runbook for **schema-per-tenant** and platform DB continuity. Align with [PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md](PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md).

## RPO / RTO targets (set per environment)

| Tier | RPO (max data loss) | RTO (time to usable) | Notes |
|------|---------------------|----------------------|--------|
| **Production** | ≤ 24 h (adjust per contract) | ≤ 4 h (adjust per contract) | Document actuals after each drill. |
| **Staging** | Best effort | Best effort | Same *procedure* as prod, smaller data. |

## Backup scope (non-negotiable)

1. **Platform / shared schema** (where `django-tenants` + `public` schema or single DB) — all tables that hold platform configuration.
2. **Every tenant schema** — schools must not be dropped from backup scope; a “restore” that only restores `public` is **invalid** for multi-tenant SaaS.
3. **Object storage** — media buckets tied to tenants (if used).

## Workers and cron

- Any job that writes to the DB must run with **explicit tenant/schema context** (or `public` only for platform). Wrong connection = silent cross-tenant corruption.
- Add new jobs to the same review checklist as HTTP routes.

## Restore drill (quarterly or each release train)

1. Take a **non-prod** snapshot label from the same backup tooling as prod.
2. Restore to an isolated DB instance.
3. Run `manage.py migrate` and smoke tests against **at least two** tenant schemas + platform.
4. Record: date, operator, RPO/RTO observed, gaps.

## Related

- Single execution source: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md)
