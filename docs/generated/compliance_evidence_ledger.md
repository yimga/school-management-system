# Compliance evidence ledger (human index)

Machine source: `compliance_evidence_ledger.json` (validated by `python scripts/verify_compliance_evidence.py`).

## Framework

- `docs/compliance/SOC2_READINESS_MAP.md`
- `docs/compliance/CONTROL_MATRIX.md`

## Operationalization (batch 1102)

- `docs/compliance/ENTERPRISE_READINESS_INDEX.md`
- `docs/compliance/ENTERPRISE_REVIEW_CHECKLIST.md`
- `docs/maintenance/VERIFIER_CI_GATE_RECOMMENDATION.md`

## Policies (required)

See `required_policy_docs` in the JSON — seven markdown files under `docs/compliance/policies/`.

## Scaling / maintenance

- `docs/scaling/CACHE_READINESS.md`
- `docs/scaling/ASYNC_JOBS_READINESS.md`
- `docs/scaling/1000_TENANT_SCALE_CHECKLIST.md`
- `docs/maintenance/REPO_COMPLEXITY_REDUCTION_SCOPE.md`

## Generated ledgers (regenerate with named scripts)

- `docs/generated/admin_gravity_audit.json` — `python scripts/audit_admin_gravity.py`
- `docs/generated/security_surface_audit.json` — `python scripts/audit_security_surface.py`
- `docs/generated/sitesettings_python_surface_audit.json` — `python scripts/audit_sitesettings_python_surface.py`
- `docs/generated/platform_inventory.json` — `python scripts/generate_platform_inventory.py --write`

## Verifier sources

Listed under `evidence` with `kind: "verifier_source"` in the JSON.

## Deployment

- `docs/deployment/DEPLOYMENT_ROLLBACK.md` (referenced from ledger `evidence`)
