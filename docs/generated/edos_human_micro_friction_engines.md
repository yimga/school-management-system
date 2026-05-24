# EdOS Human Micro-Friction Operating Engines

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_HUMAN_MICRO_FRICTION_ENGINES_READY`

## Scope

Re-architects 16 daily school operations around real human pain. Each engine has workflow + route/UI posture + data contract + tenant boundary + privacy posture + audit event + tests + external blockers if any.

## Sections

### 16 micro-friction engines

- Lost belongings QR loop — apps.schoolops.lost_belongings_asset_qr_contract (anonymous finder, parent notified, audit log)
- Geofenced drop-off coordination — apps.schoolops.dropoff_coordination_privacy_contract (opt-in, no GPS overcollection)
- Split-family communication — apps.communication.multi_custodian_routing (legal custody flag, dual dashboard, multi-signature permission slip)
- Homework support guard — apps.academics.homework_support_guard (no AI answer leakage)
- Substitute handover blueprint — apps.schoolops.substitute_handover_blueprint (temporary portal, lesson plan packet, expiry + audit)
- Micro-progress timeline — apps.evals.micro_progress_timeline (grade/attendance risk signal, proactive parent notification)
- Field trip permission-to-pay — apps.finance.permission_to_pay_workflow (event permission + payment in one flow)
- Staff reimbursement ledger — apps.payroll.reimbursement_ledger_contract (receipt capture, OCR adapter, budget code, principal approval)
- Self-healing integration sandbox — apps.interop.self_healing_integration_sandbox (schema drift, quarantine, fallback version)
- AI data cleanup pipeline — apps.migration_cloud.visual_data_cleanup_contract (row-level error highlighting, confidence scores)
- Government ghost-student verification — apps.compliance.attendance_hash_proof + verified_identity_hash
- NGO donor impact portal — apps.dportal anonymized impact metrics, no PII
- Board asset/capital leakage dashboard — apps.dashboard.board_capital_leakage
- Teacher micro-grading matrix — apps.evals.micro_grading_matrix
- Parent micro-update router — apps.communication.parent_micro_update_router
- Student polymorphic learning queue — apps.academics.polymorphic_learning_queue

### Privacy posture (non-negotiable)

- Geofenced drop-off OPT-IN ONLY; no raw GPS overcollection; geofence_class instead of raw coordinates.
- Lost belongings finder ANONYMOUS to public; parent notification via secure channel.
- Substitute portal CREDENTIALS EXPIRE on lesson end + handover audit retained.
- Health/safeguarding access AUDIT-LOGGED on every unseal.
- Donor portal NEVER shows student PII; only anonymized aggregates.

## Repo evidence (anchor paths)

- `apps/schoolops/`
- `apps/communication/`
- `apps/academics/`
- `apps/evals/`
- `apps/finance/`
- `apps/payroll/`
- `apps/interop/`
- `apps/migration_cloud/`
- `apps/compliance/`
- `apps/dashboard/`
- `apps/people/`

## Tests

- `apps/schoolops/tests/test_edos_lost_belongings_v3.py`
- `apps/schoolops/tests/test_edos_dropoff_privacy_v3.py`
- `apps/communication/tests/test_edos_multi_custodian_v3.py`
- `apps/academics/tests/test_edos_homework_guard_v3.py`
- `apps/schoolops/tests/test_edos_substitute_handover_v3.py`

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
