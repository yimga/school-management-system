# Performance and operations

This repository encodes performance expectations in verifiers and scaling checklists rather than one-off “magic” patches.

## Checklists and gates

- **Caching:** `docs/scaling/CACHE_READINESS.md`
- **Async / jobs:** `docs/scaling/ASYNC_JOBS_READINESS.md`
- **Large tenant scale:** `docs/scaling/1000_TENANT_SCALE_CHECKLIST.md`
- **Structured logging contract:** `scripts/verify_structured_logging_contract.py`

## Query discipline

- Prefer `select_related` / `prefetch_related` on hot list views; avoid N+1 in API read-models (see patterns in schools/marketplace views).
- Raw SQL and hotspot audits: `scripts/audit_query_hotspots.py`, `scripts/audit_raw_sql_usage.py` (run as part of maintenance cadence).

## Tenant demo banner

- Set `RUNMYCAMPUS_DEMO_SANDBOX=1` to show a visible **Demo sandbox** banner on authenticated portal surfaces (`apps/platform_runtime/context_processors.demo_sandbox_banner`).
