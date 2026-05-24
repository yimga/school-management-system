# EdOS Operations and Campus Logistics OS

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_OPERATIONS_LOGISTICS_OS_READY`

## Scope

Refactors schoolops + sync_engine + payroll + finance + communication + observability. Transport/fleet contract + route optimization posture + geofenced drop-off coordination (opt-in privacy-limited) + hostel/residential workflows + canteen/POS/wallet workflows + asset lifecycle + QR asset lost-and-found loop + procurement lifecycle + substitute allocation + substitute handover blueprint + health/safeguarding linkage + IoT device contract + offline field operations posture + board/institution capital leakage dashboard + teacher/staff reimbursement workflow.

## Sections

### Engine components

- Transport/fleet contract — apps.schoolops.TransportAssignment first-class + GPS contract (no fake hardware)
- Route optimization posture — apps.schoolops.route_optimization (contract; live optimizer external)
- Geofenced drop-off — apps.schoolops.dropoff_coordination_privacy_contract (opt-in, privacy-limited, NO overcollection)
- Hostel/residential — apps.schoolops.HostelAssignment first-class + warden logs
- Canteen/POS/wallet — apps.schoolops.MealPlanBalance first-class + cafeteria POS workflow
- Asset lifecycle — apps.schoolops asset_lifecycle + procurement reorder automation
- QR asset lost-and-found — apps.schoolops.lost_belongings_asset_qr_contract + asset.qr_scanned event
- Substitute allocation — apps.schoolops.substitute_payroll_integration
- Substitute handover blueprint — apps.schoolops.substitute_handover_blueprint with expiry + audit
- Health/safeguarding linkage — apps.compliance + apps.security (encrypted blob pointer + access audit)
- IoT device contract — apps.schoolops.iot_device_contract (no fake hardware readiness)
- Offline field ops — apps.sync_engine offline_field_ops_contract
- Board capital leakage dashboard — apps.dashboard.board_capital_leakage
- Teacher/staff reimbursement — apps.payroll.reimbursement_ledger_contract

## Repo evidence (anchor paths)

- `apps/schoolops/`
- `apps/sync_engine/`
- `apps/payroll/`
- `apps/finance/`
- `apps/communication/`
- `apps/observability/`
- `apps/compliance/`
- `apps/security/`

## Tests

- `apps/schoolops/tests/test_edos_transport_assignment_v2.py`
- `apps/schoolops/tests/test_edos_hostel_workflow_v2.py`
- `apps/schoolops/tests/test_edos_meal_plan_balance_v2.py`
- `apps/schoolops/tests/test_edos_lost_belongings_qr_v2.py`
- `apps/schoolops/tests/test_edos_substitute_handover_v2.py`

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
