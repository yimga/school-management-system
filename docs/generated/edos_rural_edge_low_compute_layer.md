# EdOS Rural Edge and Low-Compute Execution Layer

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_RURAL_EDGE_LAYER_READY`

## Scope

Refactors sync_engine + platform_runtime + metadata + finance + communication + academics + reports. Tenant Manifest compiler + edge runtime contract + PWA/offline posture + shared-device mode + low-bandwidth data budget + text-fragment sync + offline payment intent + USSD/IVR adapter contracts + P2P sync posture + disaster backup priority map + School-in-a-Box contract + zero-data local sync posture + offline medical/safeguarding snapshot + NO heavy native app dependency. NO fake hardware deployment claim.

## Sections

### Edge runtime primitives

- Tenant Manifest compiler — apps.sync_engine.tenant_manifest_compiler with signature/checksum + schema_version
- Edge runtime contract — apps.sync_engine.edge_runtime_contract (manifest apply + heartbeat + sync)
- PWA/offline posture — service-worker.js (131KB) + offline-queue-client + tenant_cache_key
- Shared-device mode — apps.accounts.shared_device_profile_contract + profile switcher + cache purge
- Low-bandwidth data budget — apps.sync_engine.low_bandwidth_budget (text-fragment delta, image deferral)
- Text-fragment sync — apps.sync_engine.text_fragment_sync (subscript ranges per record)
- Offline payment intent — apps.finance.offline_payment_queue + apps.sync_engine reconciliation
- USSD adapter contract — apps.communication.ussd_adapter (telecom partner external blocker)
- IVR adapter contract — apps.communication.ivr_adapter (telecom partner external blocker)
- P2P sync posture — apps.sync_engine.p2p_sync_contract (mesh between edge nodes)
- Disaster backup priority map — apps.sync_engine.disaster_backup_priority
- School-in-a-Box contract — apps.sync_engine.school_in_a_box_kernel_contract (hardware pilots external)
- Zero-data local sync posture — apps.sync_engine.zero_data_local_sync
- Offline medical/safeguarding snapshot — encrypted_blob_pointer cached locally, access audit on unseal

### Honest deferred posture (NO fake claims)

- Solar Pi-Box hardware deployment DEFERRED — kernel contract shipped, physical hardware pilots external.
- Live USSD/IVR telecom adapters DEFERRED — adapter contracts shipped, telecom partner agreements external.
- Multi-corridor edge node pilots DEFERRED — telemetry ingestion shipped, pilot ingestion external.

## Repo evidence (anchor paths)

- `apps/sync_engine/`
- `apps/platform_runtime/`
- `apps/metadata/`
- `apps/finance/`
- `apps/communication/`
- `apps/academics/`
- `apps/reports/`
- `static/js/service-worker.js`
- `apps/accounts/shared_device_cache_purge.py`

## Tests

- `apps/sync_engine/tests/test_edos_tenant_manifest_v2.py`
- `apps/sync_engine/tests/test_edos_low_bandwidth_budget_v2.py`
- `apps/sync_engine/tests/test_edos_p2p_sync_contract.py`

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
