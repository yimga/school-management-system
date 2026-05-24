# EdOS PWA-First Mobile OS Layer

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_PWA_FIRST_MOBILE_OS_READY`

## Scope

Re-architects the platform mobile strategy around PWA as launch mobile app. Native Capacitor/Tauri wrapper EXPLICITLY DEFERRED until web core stability + first-100-schools proof + PWA installability proof. This phase consumes the existing service-worker.js (131KB) + rmc-service-worker-registration.js + offline-queue-client + offline-conflicts UI shipped in prior batches.

## Sections

### PWA shell contracts (SHIPPED in prior batches; consumed here, NOT duplicated)

- Web manifest — manifest.json with installable name/short_name/icons/theme_color/background_color/display=standalone
- Service worker — static/js/service-worker.js (131KB) with monotonic CACHE_VERSION + tenant-aware cache scoping
- IndexedDB — offline-queue-client + offline-conflicts UI + tenant_cache_key isolation
- Offline command queue — apps.sync_engine.offline_queue with replay-safe upload
- Low-data sync — text-fragment delta sync + image deferral
- Shared-device mode — apps.accounts.shared_device_cache_purge contract
- Add-to-home-screen — install prompt orchestrated by rmc-service-worker-registration.js
- Offline-safe logout — tenant cache purge on session_logout event
- Stale-data banners — apps.platform_runtime stale_banner middleware + UI partial
- Conflict resolution UI — offline-conflicts UI page (apps.sync_engine surface)

### Mobile-first surfaces (route-level offline matrix)

- Teacher dashboard — offline attendance + grade entry + homework support queue
- Parent portal — offline timeline + permission slip cache + last-sync banner
- Student portal — offline polymorphic learning queue + homework support guard
- Substitute portal — temporary credentials + offline lesson plan packet + expiry-aware
- Operator — NOT mobile-offline (operator surface remains online-only by design)

### Device capability detection

- User-Agent + Client Hints (sec-ch-ua-mobile, sec-ch-ua-platform)
- Bandwidth class from navigator.connection.effectiveType (4g/3g/2g/slow-2g) — fallback to CountryRegistry.low_bandwidth_class
- PWA install state via navigator.standalone + matchMedia('(display-mode: standalone)')
- IndexedDB quota via navigator.storage.estimate()

### Deferred native wrapper roadmap (NOT shipped this batch)

- Capacitor/Tauri shell — ONLY after web core stability + first-100-schools + PWA installability proof
- Push notification — Web Push API first (with VAPID); native push notification deferred to wrapper phase
- Biometric login — WebAuthn first; native biometric deferred
- Bluetooth — WebBluetooth where supported; native deferred
- App-store submission — deferred until wrapper phase; no Swift/Kotlin rewrite
- Web remains single source of truth — native shell MUST NOT fork product logic

## Repo evidence (anchor paths)

- `static/js/service-worker.js`
- `static/js/rmc-service-worker-registration.js`
- `static/js/offline-queue-client.js`
- `static/js/offline-conflicts.js`
- `static/manifest.json`
- `apps/sync_engine/offline_queue.py`
- `apps/accounts/shared_device_cache_purge.py`
- `apps/platform_runtime/middleware_stale_banner.py`

## Tests

- `apps/platform_runtime/tests/test_edos_pwa_manifest_v2.py`
- `apps/sync_engine/tests/test_edos_pwa_offline_storage_v2.py`
- `apps/accounts/tests/test_edos_shared_device_cache_purge_v2.py`

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
