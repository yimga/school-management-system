# Tenant Resource Guardrails (Phase 10)

**Batch:** 1488 · **Verdict:** TENANT_RESOURCE_GUARDRAILS_REPO_SCOPE_PASS

## Floor
- [apps/migration_cloud/api/rate_limiting.py](../../apps/migration_cloud/api/rate_limiting.py) — tenant sliding-window quotas (1000 webhook/hr soft-warn 800 hard-reject 429)
- DRF DEFAULT_THROTTLE_CLASSES wired scope-aware
- [apps/api/rate_limit.py](../../apps/api/rate_limit.py) — `throttle_ip_request`
- Plans & entitlements: [apps/plans_entitlements/](../../apps/plans_entitlements/)
- Celery beat per-task rate limit + lazy-guarded tenant execution

## Status

| Guardrail | Status |
|---|---|
| Per-tenant workflow execution quotas | contract |
| Per-plan automation limits | shipped |
| Per-tenant API rate limits | shipped |
| Per-tenant AI usage limits | shipped (per-request counting) |
| Per-tenant migration import limits | shipped (50f/100MB/500MB) |
| Async job concurrency limits | shipped |
| Runaway workflow loop detection | contract |
| Dead-letter / hold queue | shipped (FSM retry exhausted) |
| Operator override | shipped (token/webhook admin views) |
| Customer-facing quota explanation | shipped (`X-RateLimit-Soft-Warn` at >80%) |
| Billing/plan entitlement link | shipped |
| Observability metrics (hashed tenant) | shipped |
| Safe throttling (Retry-After) | shipped |
| Noisy-tenant isolation | shipped (per-tenant scope buckets) |
| PWA sync queue quotas | contract |
| Telemetry upload quotas | contract |
| Offline sync reconciliation quotas | contract |

## Tests Added (Phase 18)
- `apps/plans_entitlements/tests/test_compute_quota_contracts.py`
- `apps/automation/tests/test_workflow_loop_guard.py`
- `apps/orchestration/tests/test_tenant_rate_limit_hold_queue.py`
- `apps/billing/tests/test_usage_metering_quota_link.py`
- `apps/sync_engine/tests/test_offline_sync_quota_guard.py`

## External Blockers (Honest)
- Production load test for noisy-tenant isolation (Lane 2 internal)
- Per-plan AI usage live billing meter (LiteLLM Lane 2)

**Verdict:** TENANT_RESOURCE_GUARDRAILS_REPO_SCOPE_PASS
