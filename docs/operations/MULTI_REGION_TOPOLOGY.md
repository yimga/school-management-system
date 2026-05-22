# Multi-region topology (honest operator runbook)

**GEOS-99 batch 1384 (AWS pillar).** This document describes the **current** RunMyCampus deployment topology and the path to multi-region without claiming a second live region that does not exist.

## Current default (single primary region)

| Layer | Default posture |
|-------|-----------------|
| **Web + workers** | One Render (or operator) primary region per environment |
| **PostgreSQL** | Single primary database; tenant schemas on shared cluster |
| **Redis / Celery** | Co-located with web in the same region |
| **Tenant routing** | Host-based + path-based; `School.regional_cluster` selects DB alias when configured |
| **Regulatory region** | `School.data_region` + optional `School.settings["data_residency"]` |

RunMyCampus is **production-ready in single-region mode**. Multi-region is an **ops expansion**, not a repo blocker.

## Failover (honest)

1. **RTO/RPO targets** — See `docs/operations/SLA.md` and `GET /api/roadmap/rpo-rto/` contract.
2. **Database** — Restore from latest verified backup (`scripts/restore_drill.py`); no automatic cross-region active-active today.
3. **DNS / host routing** — Operator updates `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and tenant custom domains after cutover.
4. **Cache invalidation** — Run tenant resolution cache purge after region flip (`apps/schools/signals_tenant_cache.py`).

## Adding a second region (operator checklist)

1. Provision Postgres replica or second cluster in target region.
2. Register alias in `DATABASES` + map `School.regional_cluster` / `data_region` for pilot tenants.
3. Run `python manage.py verify_data_residency --strict` on pilot slugs.
4. Enable `ENABLE_MULTI_REGION=1` only after connectivity and backup drills pass.
5. Record evidence in `var/evidence/geos-99/compliance/residency_<date>.json`.

## Related docs

- `docs/PHASE_I_MULTI_REGION_AND_DEPLOY.md` — engineering phases
- `docs/TENANT_ISOLATION_AND_DATA_RESIDENCY.md` — tenant isolation + residency
- `docs/deployment/RENDER_DEPLOYMENT_RUNBOOK.md` — Render deploy

## What this doc does **not** claim

- No second live region is implied by this repository state.
- SOC 2 / ISO attestations remain Lane 2 (`docs/compliance/`).
