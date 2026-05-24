# EdOS Tenant Resource Governor and Compute Economy

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_RESOURCE_GOVERNOR_READY`

## Scope

Re-architects lifecycle + plans_entitlements + billing + automation + orchestration + events + analytics + apicenter + sync_engine + migration_cloud + AI around per-tenant compute budget, per-plan workflow budget, API rate limits, AI token/task quotas, migration import budgets, report/export limits, async job concurrency, runaway workflow detection, tenant hold queue, operator override, usage-to-billing linkage, abuse alerts, no single-tenant platform degradation, PWA sync throttling, offline replay throttling, telemetry quota, low-bandwidth priority lanes.

## Sections

### ResourceQuotaContext fields

- plan_id — tenant subscription plan from plans_entitlements
- ai_token_budget_remaining — per-month token budget from apicenter rate limiter
- workflow_minutes_remaining — automation budget
- export_count_remaining — report/export budget
- async_job_concurrency_remaining — orchestration concurrency cap
- pwa_sync_quota_remaining — sync_engine offline replay throttle
- telemetry_quota_remaining — observability quota
- abuse_score — composite anomaly score for noisy-tenant isolation

### Enforcement points

- orchestration.tenant_rate_limit_hold_queue — throttle to hold queue, never silent drop
- automation.workflow_loop_guard — runaway detection + circuit break
- billing.usage_metering_quota_link — every quota consumption emits billing event
- sync_engine.offline_sync_quota_guard — PWA replay throttle
- apicenter.ai_token_budget_guard — AI token quota at gateway
- Operator override — explicit override_token + audit_event required; never silent override

## Repo evidence (anchor paths)

- `apps/plans_entitlements/`
- `apps/billing/`
- `apps/automation/`
- `apps/orchestration/`
- `apps/lifecycle/`
- `apps/sync_engine/`
- `apps/apicenter/`
- `apps/observability/`

## Tests

- `apps/plans_entitlements/tests/test_edos_compute_quota_v2.py`
- `apps/orchestration/tests/test_edos_hold_queue_throttling.py`
- `apps/billing/tests/test_edos_usage_metering_quota_link_v2.py`

## External blockers (deferred — repo cannot fix)

- live PSP settlement reconciliation per corridor
- SOC2 Type II PDF
- MoE / Ministry of Education per-country live integrations
- WhatsApp Business platform Meta verification
- USSD telecom partner agreements per country
- native push notification wrapper (Capacitor/Tauri) — deferred until first-100-schools proof
- live LiteLLM API keys on Render
- Render SHA parity live verification
- multi-corridor pilot ingestion
- Postgres RLS enforced in production (current local env is SQLite)

## PWA-first posture

PWA is the launch mobile strategy. Native iOS/Android apps are explicitly DEFERRED until web core stability + first-100-schools proof + PWA installability proof. Service worker + manifest + IndexedDB + offline queue shipped in prior batches; this re-architecture preserves and consumes that infrastructure rather than forking.

## Honesty notes

- Repo-scope contracts only — no live vendor integration claims.
- Existing canonical models preserved; metadata layer absorbs tenant variance per architecture correction.
- External blockers listed above remain unchanged by batch 1489.
