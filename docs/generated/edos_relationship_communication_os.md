# EdOS Relationship and Communication OS

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_RELATIONSHIP_COMM_OS_READY`

## Scope

Refactors communication + sales + customers + customersuccess + feedback + student360 + people into a relationship operating layer: stakeholder graph, admissions pipeline, lifecycle timeline, parent communication history, teacher availability guard, omnichannel router, safeguarding audit hash, support case linkage, alumni/donor extension posture, retention signals, feedback-to-roadmap loop, AI workflow support (safe), split-family communication, right-to-disconnect queue, parent micro-updates, NGO/donor impact portal linkage, government reporting relationship posture.

## Sections

### Engine components

- Stakeholder graph — apps.people custody + apps.student360 relationships
- Admissions pipeline — apps.sales admissions Kanban + lead scoring
- Lifecycle timeline — apps.student360 LifecycleTimeline with attendance/grades/comms threads
- Parent communication history — apps.communication ParentCommHistory append-only
- Teacher availability guard — apps.communication availability_guard with right-to-disconnect buffer
- Omnichannel router — apps.communication ChannelAdapter registry (email/push/SMS/WhatsApp/Telegram/IVR/USSD contracts)
- Safeguarding audit hash — apps.communication safeguarding_audit_hash (HMAC-SHA512 immutable timeline)
- Support case linkage — apps.customersuccess.support_crm_linkage
- Alumni/donor extension — apps.dportal donor program visibility (gated by consent)
- Retention signals — apps.evals risk_drivers + apps.customersuccess retention alerts
- Feedback-to-roadmap loop — apps.feedback voice-of-customer router
- Split-family communication — apps.communication multi_custodian_routing
- Right-to-disconnect queue — apps.communication out_of_hours_queue with release_at scheduling
- Parent micro-updates — apps.communication parent_micro_update_router
- NGO/donor impact portal linkage — apps.dportal anonymized impact metrics
- Government reporting relationship posture — apps.compliance.gov_export_envelope (anonymized, jurisdiction-tagged)

## Repo evidence (anchor paths)

- `apps/communication/`
- `apps/sales/`
- `apps/customers/`
- `apps/customersuccess/`
- `apps/feedback/`
- `apps/student360/`
- `apps/people/`

## Tests

- `apps/communication/tests/test_edos_relationship_os_router.py`
- `apps/student360/tests/test_edos_lifecycle_timeline_v2.py`
- `apps/customersuccess/tests/test_edos_retention_signals_v2.py`

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
