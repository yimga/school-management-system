# Rural / Offline Edge + PWA Gap Closure (Phase 5)

**Batch:** 1488 · **Verdict:** RURAL_OFFLINE_EDGE_REPO_SCOPE_PASS

## PWA Infrastructure (Shipped)
- [service-worker.js](../../static/js/service-worker.js) — 131 KB, cache `sms-v3.84.7` (Phase 22 bumps to `sms-v3.85.0`)
- [rmc-service-worker-registration.js](../../static/js/rmc-service-worker-registration.js)
- Manifest emitted by all 4 dashboard shells; `scan_pwa_manifest_coverage.py` baseline 0
- Offline form queue via `data-rmc-offline-form` markers
- Conflicts UI: `/portal/offline/conflicts/`
- `verify_service_worker_version.py` enforces CACHE_VERSION monotonicity

## Rural / Offline Edge Contracts
| Item | Status | Notes |
|---|---|---|
| Tenant Manifest compiler | contract documented | `apps/sync_engine/` extension contract |
| Edge runtime contract | documented | School-in-a-Box deployment posture |
| P2P sync | contract | Africa regional adapter (Phase 15) |
| Low-bandwidth budget | shipped (contract) | text-first sync + image deferral + canonical-JSON tiny envelopes |
| Shared-device profile | contract | PIN/pattern + cache purge on logout |
| USSD adapter | contract | Phase 15 Africa adapter |
| IVR adapter | contract | Phase 15 Africa adapter |
| Solar Pi-box deployment | contract | partnership dependency |
| Offline payment queue | shipped | OfflinePaymentIntent + bursar bulk approve |
| Offline attendance/grade queue | shipped | offline-queue-client |

## Native Deferment (Honest)
- Native iOS/Android **NOT BUILT THIS BATCH**
- Capacitor/Tauri wrapper deferred until first 100 schools stable + PWA installability proven
- Web remains single source of truth; wrapper would not fork product logic
- Deferred features pending wrapper: native push, biometric, Bluetooth, app-store presence

## Tests Added (Phase 18)
- `apps/sync_engine/tests/test_tenant_manifest_compiler.py`
- `apps/sync_engine/tests/test_offline_edge_sync_contract.py`
- `apps/sync_engine/tests/test_low_bandwidth_budget.py`
- `apps/sync_engine/tests/test_shared_device_profile_contract.py`
- `apps/sync_engine/tests/test_offline_payment_sync_contract.py`
- `apps/sync_engine/tests/test_offline_queue_contract.py`
- `apps/platform_runtime/tests/test_pwa_manifest.py`
- `apps/platform_runtime/tests/test_pwa_offline_storage_contract.py`
- `apps/platform_runtime/tests/test_pwa_tenant_cache_safety.py`
- `apps/accounts/tests/test_shared_device_cache_purge.py`

## External Blockers (Honest)
- live solar Pi-box deployment partner
- live USSD telecom partner + short-code allocation
- live IVR vendor setup
- live device-matrix Playwright (iOS Safari + Android Chrome + Edge desktop)
- MaxMind GeoLite2-City `.mmdb` deployment to Render (operator action per [docs/GEOIP_DEPLOYMENT.md](../GEOIP_DEPLOYMENT.md))

**Verdict:** RURAL_OFFLINE_EDGE_REPO_SCOPE_PASS
