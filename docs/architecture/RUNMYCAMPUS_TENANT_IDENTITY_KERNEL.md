# RunMyCampus Tenant Identity Kernel

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

## Summary

Kernel-level tenant isolation: JWT/session tenant binding + TenantContext + ActorContext + Postgres RLS posture + SQLite fallback + impersonation ledger + tenant cache isolation + tenant-scoped AI/PWA/telemetry/migration/template-preview/resource-quota contexts. The database/runtime must protect tenant boundaries even if application-level code makes a mistake.

## See also

- `docs/generated/edos_tenant_identity_kernel.{json,md}` — kernel contract
- `docs/generated/tenant_identity_federation_rls_audit.{json,md}` — Prompt 1 baseline
- `apps/tenancy/sql/` — RLS policy SQL (Postgres apply at deploy)

