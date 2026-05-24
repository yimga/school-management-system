# RunMyCampus PWA-First Mobile OS

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

## Summary

The platform launches as web + PWA. Native iOS/Android apps are DEFERRED until web core stability + first-100-schools + PWA installability proof. Service worker, manifest, IndexedDB, offline queue, shared-device mode, low-data sync, and conflict resolution UI are all shipped infrastructure that this OS layer consumes — not duplicated.

## Mobile strategy phases

**Phase 1 (current):** Web + PWA first. Add-to-home-screen + installable manifest + service worker + IndexedDB + offline sync + low-data mode + shared-device mode + PWA install prompts. No app-store dependency. No 100MB downloads. Instant global updates through web refresh.

**Phase 2 (deferred):** Hybrid native wrapper via Capacitor/Tauri/WebView shell ONLY after Phase 1 stability. No Swift/Kotlin rewrite. Web remains single source of truth. Native wrapper unlocks push, biometric login, Bluetooth, app-store presence. Native shell MUST NOT fork product logic.

## See also

- `docs/generated/edos_pwa_first_mobile_os.{json,md}` — full PWA OS contract
- `docs/generated/pwa_first_mobile_launch_strategy.{json,md}` — Prompt 1 Phase 5 baseline
- `static/js/service-worker.js` (131KB) — shipped service worker
- `static/manifest.json` — installable manifest

