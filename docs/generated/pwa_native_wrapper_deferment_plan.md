# PWA Native Wrapper Deferment Plan (Batch 1506)

**Decision:** DEFER native wrappers (Capacitor / Tauri / WebView) until PWA-first stability gates are met.

## Not building in this batch

- iOS native app (Swift / SwiftUI / WKWebView wrapper)
- Android native app (Kotlin / Compose / Android WebView wrapper)
- Capacitor wrapper
- Tauri mobile wrapper

## Preserved companion siblings (IT / operator appliances — NOT consumer mobile apps)

- `companion-extension/` (MV3 browser ext)
- `companion-tauri/` (Tauri desktop appliance)
- `companion-docker/` (FastAPI container appliance)

## Promote to native when ALL true

1. ≥100 active schools running stable on PWA
2. Install-prompt success ≥70% on Android Chrome (browser-recorded)
3. Offline write-queue replay >95% success (browser-recorded)
4. Counsel signoff on push-notification PII handling
5. Operator-team capacity for app-store review cycles
6. App-store listing assets + brand kit signed off by marketing

## Promotion order when unblocked

1. Android (Capacitor wrap; Play Store internal track first)
2. iOS (Capacitor wrap; Apple TestFlight first)
3. Push-notification capability after counsel signoff
4. Native bridge plugins ONLY if PWA can't satisfy (e.g., contact import)
