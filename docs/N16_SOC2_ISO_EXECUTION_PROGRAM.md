# N16 — SOC 2 / ISO execution program (trust & compliance)

**Purpose:** Close the *product* side of N16 (RUNMYCAMPUS §0.1.5 / north star): documented control themes, evidence map, and operator checklist. **Formal attestation** (SOC 2 Type II report, ISO 27001 certificate) is **external** — executed by a qualified auditor after this program is green.

**Trust center:** In-app `super:trust_center` — certifications / attestations card links here and to [MARKETPLACE_REGION_AND_CERT_MINIMUMS.md](MARKETPLACE_REGION_AND_CERT_MINIMUMS.md).

## 1. Control themes → repository evidence

| Theme | What auditors expect | Where we prove it (code / docs) |
|-------|----------------------|----------------------------------|
| Access control | RBAC, least privilege, admin boundaries | `apps/accounts/permissions.py`; tenant isolation tests; `public_endpoint_audit.md` |
| Change management | Reviewed deploys, migrations | `pre_deploy_gate.sh`; `RELEASE_CHECKLIST.md`; `SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md` |
| Logging & monitoring | Audit trail, security events | `PlatformEventLog`; structured logging; `SLO_TARGETS_AND_OBSERVABILITY.md` |
| Data protection | Encryption in transit, residency narrative | `TENANT_ISOLATION_AND_DATA_RESIDENCY.md`; trust center |
| Incident response | Documented process | Trust center incidents / breach narrative; `SECURITY_REVIEW_LOG.md` |
| Vendor / sub-processors | Inventory + review | `provider_abstraction_audit.md`; `INTEGRATION_PARTNER_TRUST_SIGNALS.md` |

## 2. Execution phases (operator)

1. **Gap assessment** — Map org policies to the table above; open tickets for gaps.  
2. **Evidence pack** — Export runbooks, last `pre_deploy_gate` record (`docs/generated/pre_deploy_gate_run.txt`), and trust-center screenshots.  
3. **Readiness review** — Security + eng sign-off (internal).  
4. **External audit** — Engage firm; SOC 2 Type II or ISO 27001 scope statement.  
5. **Publish** — Update trust center with report/certificate metadata (no claim until issued).

## 3. SOT closure language

- **Repo “executed”** = this program is maintained and evidence links stay current.  
- **Market “executed”** = attestation on file; update N16 checkbox to full `[x]` only with **report ID + date** in trust center or release notes.

**Owner:** Security / platform ops (assign per org).
