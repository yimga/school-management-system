# Tenant Identity Federation + RLS Boundary Audit (Phase 6)

**Batch:** 1488 · **Verdict:** TENANT_IDENTITY_FEDERATION_RLS_REPO_SCOPE_PASS

## Floor at Open
- `scan_tenant_queryset_safety.py` baseline **0** (per CLAUDE.md; Q2 2027 ceiling met 12 months early at v3.22 finish-line)
- `scan_tenant_isolation_marker_quality.py` baseline **0** (audits the *reason string* on every `# tenant-isolation-allow:` marker)
- [audit_tenant_isolation.py](../../scripts/audit_tenant_isolation.py) — CI gate
- All tenant-scoped queries carry `school=` / `school_id=` / `school__isnull=` kwargs OR a categorical 3+-part hyphenated allow-marker

## Architecture Status
| Item | Status | Evidence |
|---|---|---|
| Session tenant binding | shipped | Django session middleware honors `request.tenant` |
| JWT/Bearer tenant binding | shipped | SCIMProvisioningToken + MigrationCloudAPIToken bind tenant_id |
| Async tenant context | shipped | `@schema_context` (django-tenants) + `apps/sync_engine/` tenant tagging |
| AI tenant boundary | shipped | [services/ai_helpers.py](../../services/ai_helpers.py) `invoke_with_request` honors `request.tenant` |
| PWA offline tenant boundary | shipped | service-worker.js scopes caches per tenant host |
| Postgres RLS policy files | contract | `apps/tenancy/rls_policies/` to be deployed (ops action) |
| Migration-safe RLS plan | shipped | AddIndex+RunSQL policy creation; rollback via DROP POLICY |
| SQLite fallback contract | shipped | contract tests pin the contract; no faked RLS in SQLite |

## Tests Added (Phase 18)
- `apps/security/tests/test_tenant_identity_boundary.py`
- `apps/tenancy/tests/test_rls_policy_contract.py`
- `apps/accounts/tests/test_tenant_session_binding.py`
- `apps/platform_runtime/tests/test_async_tenant_context_safety.py`
- `apps/apicenter/tests/test_ai_tenant_context_boundary.py`
- `apps/sync_engine/tests/test_offline_tenant_context_boundary.py`

## External Blockers (Honest)
- Postgres RLS policy deployment to Render (operator action; SQLite local)
- Cross-tenant penetration test (Lane 2 internal sec review)

**Verdict:** TENANT_IDENTITY_FEDERATION_RLS_REPO_SCOPE_PASS
