# Tenant isolation & data residency

**Foundation §0.3 pillar 1 — verifiable.**

## Isolation

- **RLS:** `apps/schools/rls_context.py` — `set_rls_school_id` / reset (session **`SET`/`RESET`** SQL in **`repositories/rls_context_repository.py`**); middleware applies tenant context. Retained catalog/session SQL elsewhere lives only in the **six** §2.4 paths in `docs/raw_sql_audit.md` §1 / `raw_sql_allowlist.json`.
- **Contract:** Tenant tests `test_tenant_isolation_and_provisioning`, `test_rls_context`.
- **Residency fields:** `apps/schools/tests/test_school_data_residency_contract.py` — `School.compliance_region`, `dedicated_db_alias`, `default_region`.
- **Lint:** `lint_tenant_settings`, `lint_bounded_context_imports`.

## Residency (operational)

| Control | Mechanism |
|---------|-----------|
| **Region** | `School.default_region`, `RegionConfig`, deployment region (hosting). |
| **Data location** | Primary DB region chosen at deploy; dedicated_db_alias for large tenants (schema). |
| **GDPR / FERPA** | Trust center + `INTEGRATION_PARTNER_TRUST_SIGNALS.md`; DPA with customer. |
| **Export / delete** | GDPR tools in compliance app; audit export in super trust flow. |

**Next engineering hardening:** per-tenant row-level “data_region” flag + block cross-region queries in internal APIs (when multi-region DBs exist).
