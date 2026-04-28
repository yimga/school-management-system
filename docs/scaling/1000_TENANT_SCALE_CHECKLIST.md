# 1000+ tenant scale checklist (architecture)

Use as a review agenda before promising large fleet sizes. Items are **not** all implemented to enterprise SaaS standard in-repo.

## Database

- [ ] Connection pool sizing per app tier (PgBouncer / pooler — ops).
- [ ] Index review on `School`, `StudentProfile`, `Evaluation`, invoice tables (run `EXPLAIN` on hottest queries from `docs/generated/query_hotspots_audit.md` once produced).
- [ ] Partitioning strategy for append-only logs (external decision).

## Tenant isolation

- [ ] Confirm no raw SQL bypasses `school_id` / RLS GUC (`scripts/audit_raw_sql_usage.py`, `scripts/audit_tenant_isolation.py`).
- [ ] Manager-host routes never assume `request.school` from tenant cookie alone (see middleware tests).

## Caching

- [ ] Read `CACHE_READINESS.md`; adopt only with tenant-prefixed keys.

## Async

- [ ] Read `ASYNC_JOBS_READINESS.md`; offload heavy report jobs before SLA promises.

## Media

- [ ] Object storage + CDN for static/media; tenant-scoped prefixes.

## Backup / restore

- [ ] RPO/RTO defined per customer; test restores.

## Monitoring

- [ ] Per-tenant error rate dashboards; synthetic checks on login + portal.

## Rate limiting

- [ ] API and webhook endpoints throttled at edge (gateway config — outside repo).

## Admin / control-plane performance

- [ ] Paginate heavy admin changelists; use CP hubs for operator workflows (`audit_admin_gravity.py`).
