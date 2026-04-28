# Enterprise readiness index

This index ties together **readiness artifacts** for sales conversations, security questionnaires, and internal reviews. It does **not** assert SOC 2 Type II certification, ISO certification, or any third-party attestation.

## SOC 2 readiness status

**Documentation structure:** Present. Maps trust principles to repo evidence and gaps:

- `docs/compliance/SOC2_READINESS_MAP.md`
- `docs/compliance/CONTROL_MATRIX.md`

**Interpretation:** The repository supports *internal* gap analysis and questionnaire responses. Formal audit engagement is out of scope for this document.

## Policy inventory

Seven repo-local policies under `docs/compliance/policies/`:

| Document |
| --- |
| `ACCESS_CONTROL_POLICY.md` |
| `CHANGE_MANAGEMENT_POLICY.md` |
| `INCIDENT_RESPONSE_POLICY.md` |
| `BACKUP_AND_RESTORE_POLICY.md` |
| `DATA_RETENTION_POLICY.md` |
| `VENDOR_RISK_POLICY.md` |
| `SECURITY_MONITORING_POLICY.md` |

Paths are enforced by `python scripts/verify_compliance_evidence.py` via `docs/generated/compliance_evidence_ledger.json`.

## Evidence ledger status

Machine-readable ledger + human index:

- `docs/generated/compliance_evidence_ledger.json`
- `docs/generated/compliance_evidence_ledger.md`

The verifier confirms referenced files exist; it does not certify operational effectiveness.

## Security audit status

| Artifact | Generator |
| --- | --- |
| `docs/generated/security_surface_audit.json` | `python scripts/audit_security_surface.py` |

Heuristic scan (e.g. `csrf_exempt`, `AllowAny`, raw SQL hooks, subprocess, auth decorators). Treat as **inventory**: review JSON for `needs_review` / `violation` tiers before relying on summaries alone.

## Tenant isolation status

| Artifact | Generator |
| --- | --- |
| `docs/generated/tenant_isolation_audit.json` | `python scripts/audit_tenant_isolation.py` |

Classification is visibility-first; it does not prove absence of cross-tenant bugs.

## Scale readiness status

| Topic | Doc |
| --- | --- |
| Cache strategy (no mandatory implementation) | `docs/scaling/CACHE_READINESS.md` |
| Async / jobs readiness | `docs/scaling/ASYNC_JOBS_READINESS.md` |
| Multi-tenant checklist | `docs/scaling/1000_TENANT_SCALE_CHECKLIST.md` |
| Query hotspots (static hints) | `docs/generated/query_hotspots_audit.md` (+ JSON) |

## Known gaps

Concrete gaps vary by release; authoritative **counts and rows** live in generated JSON under `docs/generated/` (security surface, tenant isolation, raw SQL, subprocess, repo complexity, Gilead references). Re-run the named audit scripts after material changes.

Cross-cutting themes to watch:

- Raw SQL and subprocess usage require path-by-path review (`audit_raw_sql_usage.py`, `audit_subprocess_usage.py`).
- Legacy naming (`audit_gilead_references.py`, especially `--strict-public` for customer-visible templates).
- Admin versus control-plane routing (`audit_admin_gravity.py`, `audit_admin_usage_extended.py`).

## Next review cadence

| Review | Suggested cadence |
| --- | --- |
| Evidence ledger + policy paths | After each compliance-doc or deployment-doc change (`verify_compliance_evidence`) |
| Security / tenant / SQL / subprocess audits | Quarterly or before major release |
| Enterprise questionnaire / customer security pack | Per deal; refresh when architecture or data flow changes |

Use `docs/compliance/ENTERPRISE_REVIEW_CHECKLIST.md` as the operator-facing runbook.
