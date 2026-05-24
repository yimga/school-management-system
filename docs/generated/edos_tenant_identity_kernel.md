# EdOS Tenant Identity / RLS Kernel

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_TENANT_IDENTITY_KERNEL_READY`

## Scope

Re-architects tenant isolation into a kernel-level boundary. JWT/session tenant binding + TenantContext + ActorContext + Postgres RLS posture + async tenant context propagation + management command tenant safety + raw SQL guardrails + impersonation ledger + tenant cache isolation + tenant-scoped AI context + tenant-scoped offline/PWA cache + tenant-scoped telemetry packets + tenant-scoped migration context + tenant-scoped template preview + tenant-scoped resource quota.

## Sections

### Kernel boundary contracts

- JWT/session tenant binding — TenantContext extracted at request middleware; cryptographic binding (HMAC) prevents forged tenant_id swaps.
- Async tenant context propagation — TenantContext passed explicitly as first arg to every job; no thread-local reads.
- Postgres RLS — policy SQL files at apps/tenancy/sql/ + Postgres-tagged tests + SQLite fallback contract tests.
- Management command tenant safety — every manage.py command that touches tenant data MUST require --tenant <id> arg + validate.
- Raw SQL guardrails — apps.security tenant scanner enforces baseline 0 raw SQL outside whitelisted ORM-backed paths.
- Impersonation ledger — apps.accounts.impersonation_audit_event with HMAC-SHA512 root_key_signature.
- Tenant cache isolation — cache keys prefixed with TenantContext.tenant_id + manifest_hash.
- Tenant-scoped AI context — apicenter.ai_helpers redacts cross-tenant data; never crosses gateway boundary.
- Tenant-scoped offline/PWA cache — tenant_cache_key in IndexedDB; purged on session_logout event.
- Tenant-scoped telemetry packets — observability emits with TenantContext.tenant_id; NO PII by default.
- Tenant-scoped migration context — migration_cloud quarantine isolated per tenant_id.
- Tenant-scoped template preview — brand_experience preview routes _gate_operator_only enforces 404 on cross-tenant preview.
- Tenant-scoped resource quota — plans_entitlements quota_context per tenant_id.

### Postgres RLS posture (DEFERRED — environment is SQLite)

- RLS policy SQL files at apps/tenancy/sql/rls_*.sql — created, applied to Postgres at deploy.
- Migration plan — RLS policies applied via apps.tenancy.migrations.00XX_rls_policies (Postgres only — SQLite skip).
- Postgres-tagged tests — @postgres_required decorator marks RLS contract tests; SimpleTestCase fallback documents the contract.
- SQLite fallback — application-level tenant filter via TenantManager + tenant scanner baseline 0 (already shipped).
- Deployment checklist — Postgres production deployment runs RLS policy application script before traffic.

## Repo evidence (anchor paths)

- `apps/tenancy/`
- `apps/accounts/`
- `apps/security/`
- `apps/platform_runtime/`
- `services/ai_helpers.py`
- `apps/sync_engine/`
- `apps/migration_cloud/`
- `apps/brand_experience/`
- `apps/plans_entitlements/`
- `apps/observability/tracing.py`

## Tests

- `apps/security/tests/test_edos_tenant_kernel_boundary.py`
- `apps/tenancy/tests/test_edos_rls_policy_contract_v2.py`
- `apps/accounts/tests/test_edos_impersonation_ledger.py`

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
