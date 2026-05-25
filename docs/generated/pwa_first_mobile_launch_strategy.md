# PWA-First Mobile Launch Strategy (Batch 1506)

**Strategy:** PWA-first. Native wrappers (Capacitor / Tauri / WebView) **DEFERRED** until:

1. ≥100 active schools running stable on PWA
2. Browser-recorded install-prompt success ≥70% on Android Chrome
3. Browser-recorded offline write-queue replay >95% success
4. Counsel signoff on push-notification PII handling
5. Operator-team capacity for app-store review cycles

## Artifact state

| File | Status |
| --- | --- |
| `static/manifest.json` | present |
| `static/manifest-portal.json` | present |
| `static/js/service-worker.js` | present (131 KB) |
| `static/js/rmc-service-worker-registration.js` | present |

Service worker version: `sms-v3.91.0-runtime-proof-hardening-2026-05-24` (monotonic; baseline at `var/security-audit-baseline-service-worker-version.json`).
