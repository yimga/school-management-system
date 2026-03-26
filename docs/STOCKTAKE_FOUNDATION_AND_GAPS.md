# Stocktake: foundation (§0.3) and remaining gaps

**As of:** 2026-03-25 (engineering snapshot; doc closure pass aligned with SOT §0.3 / §11.4 vocabulary). **Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§0.3.1** (codebase evidence table), **§0.3.2** (competitor map), **§0.3.3** (BR execution queue); ledger [docs_truth_ledger.md](docs_truth_ledger.md). **CI:** `python scripts/verify_sot_pillar_evidence.py`.

## Summary

| Area | Status | Notes |
|------|--------|--------|
| Runtime / bounded contexts / metadata | **MET** | Lint + contract tests; lineage API/UI |
| Multi-tenant isolation / residency | **MET** | Doc + `test_school_data_residency_contract` |
| Ecosystem (packs, marketplace, trust, dev API) | **MET** (doc+code) | Manifest, `/developers/api-docs/`, sandbox, cert minimums doc |
| Security / public endpoints / rate limits | **MET** | FERPA/GDPR/retention/incidents public pages; hot-path limits |
| External API / webhooks | **MET** | Manifest; idempotency + dead-letter; **`test_api_v1_route_contract`** sweeps all named v1 routes (anonymous GET ≠ 2xx) |
| Internal API / events | **Baseline MET** | `INTERNAL_API_STANDARDS`; **PlatformEventLog** + `emit_platform_event` (pack apply/rollback); **super trust → Platform events** UI |
| Structural tech debt (mega-files) | **MET (baseline)** | BR-12 splits + `lint_mega_files`; further splits = §11.4 hygiene (SOT §0.3 foundation row) |
| Premium UX / sidebar / touring | **MET (repo program)** | Phase H + operator E2E gates + [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md) repo checklist; staging/product sign-off = release process **N/A** |
| Clever/ClassLink **native** vendor APIs | **BLOCKED** | Partnership + credentials; OneRoster + Bearer shipped |

## Closed this cycle (examples)

- **super_audit_export:** `trust_center_url` was undefined on first render → **fixed** (NameError risk).
- **Trust center:** **Platform events (7d)** card + **`/super/trust/platform-events/`** log (PlatformEventLog).
- **API v1 contract:** Programmatic test over **all named** `urls_v1` routes (except public manifest); **pre_deploy_gate** includes `test_api_v1_route_contract` + manifest + contract smoke.

## Remaining gaps (honest)

1. **Structural tech debt (§11.4)** — Ongoing mega-file splits and orchestration clarity; track via `lint_mega_files` + LEGACY_PATH_INVENTORY; **§12 spine MET**.
2. **Premium bar (release N/A)** — Repo gates + BR-13 checklist green; full staging/product sign-off is per-release, not an engineering **PARTIAL** row.
3. **OpenAPI snapshot diff** — Route contract tests auth surface; optional next step: export `/api/schema/` and snapshot in CI.
4. **Full event bus** — PlatformEventLog is baseline; Celery/outbox for every long-running flow remains incremental where not already wired.
5. **Interop optionals** — OIDC back-channel logout, FAPI, district roster webhooks, guided SIS import+diff UI, etc. — per WORLD_CLASS_TRIPLE_WEDGE / INTEGRATION_BEYOND_REACH.

## How to re-verify

```bash
bash scripts/pre_deploy_gate.sh   # includes API v1 contract tests
python manage.py test apps.api.tests.test_api_v1_route_contract --keepdb --noinput
```
