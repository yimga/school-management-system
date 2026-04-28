# SOC2 readiness map (internal — not a certification)

This document maps common SOC2-style themes to **evidence that already exists in this repository**. It does **not** claim SOC2, ISO, or any third-party attestation. Use it to plan audits and customer security questionnaires.

Canonical execution context: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

## Security

| Topic | Repo evidence | Gap / owner action |
| --- | --- | --- |
| Access control (RBAC, staff vs tenant) | `apps/accounts/`, `apps/schools/control_plane.py`, middleware in `apps/schools/middleware.py` | Formal access review cadence + external pen test not in repo |
| Authentication | `apps/accounts/`, MFA paths, SAML/OIDC modules | IdP-specific runbooks live partly in `docs/deployment/` |
| Authorization on APIs | DRF permission classes; `scripts/audit_security_surface.py` (AllowAny hits) | Map each AllowAny to documented rationale |
| Tenant isolation | `TenantMiddleware`, `apps/schools/host_routing.py`, `scripts/audit_tenant_isolation.py` | DB-level RLS / connection pooling at scale — see scaling checklist |
| Change management | Git history, PR process in `CONTRIBUTING.md`, SOT §11.4 batches | Formal CAB records external to repo |
| Security monitoring | `apps/platform_runtime` observability hooks, incident models | 24/7 SOC runbook external |

## Availability

| Topic | Repo evidence | Gap |
| --- | --- | --- |
| Health endpoints | `/health`, `/ready/` prefixes in middleware allowlists | Multi-region failover not specified in code |
| Deployment | `render.yaml`, `docs/deployment/*` | SLA definitions are customer-specific |

## Confidentiality

| Topic | Repo evidence | Gap |
| --- | --- | --- |
| Data in transit | HTTPS assumptions, `SECURE_*` settings in `config/settings.py` | Certificate rotation ops external |
| Tenant data separation | Subdomain + `request.school` resolution, schema notes in tenancy docs | Encryption-at-rest policy for DB/backups — ops |

## Privacy

| Topic | Repo evidence | Gap |
| --- | --- | --- |
| DSAR / compliance packs | Evidence pack commands under `apps/compliance` (if present) + tests | Jurisdiction-specific DPA templates external |
| Audit trails | `ConfigMutationAuditLog`, finance/portal audit patterns | Retention enforcement — see `DATA_RETENTION_POLICY.md` |

## Processing integrity

| Topic | Repo evidence | Gap |
| --- | --- | --- |
| Report / grade integrity | `apps/reports`, `apps/academics`, report card builder tests | E2E signing of PDFs — product roadmap |
| Financial postings | `apps/finance` with tests | External accountant controls |

---

**Next steps (non-blocking):** maintain `docs/generated/compliance_evidence_ledger.json`, run `python scripts/verify_compliance_evidence.py` in CI after doc moves, and extend `CONTROL_MATRIX.md` when new controls ship.
