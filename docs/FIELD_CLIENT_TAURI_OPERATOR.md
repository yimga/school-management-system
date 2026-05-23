# Tauri Field Client — operator runbook (SODP batch 1409)

The Field Client extends `companion-tauri/` to load tenant teacher portal flows in a WebView while storing offline capability tokens in **Stronghold** (stub command documented in `companion-tauri/README.md`).

## Operator workflow

1. Install the signed `.dmg` / `.msi` from a `companion-tauri-v*` GitHub Release (see `docs/COMPANION_SIBLINGS_SIGNED_RELEASE.md`).
2. Sign in online once — the portal mints a scoped offline token at `/api/v1/devices/offline-token/`.
3. Set a device PIN — the token is sealed with WebCrypto / Stronghold; **no password hash is stored locally**.
4. Use attendance and grade entry offline; the outbox syncs via existing DRF APIs when connectivity returns.

## Environment

- `window.RMC_FIELD_CLIENT=1` is injected in WebView for UI affordances.
- Hub discovery: `_runmycampus-hub._tcp.local.` when `RMC_DEPLOYMENT_PROFILE=hybrid` (see `docs/LOCAL_HUB_MODE.md`).

## Honest Lane 2 residuals

- Apple notarization and Windows Authenticode ship via release workflows; not claimed corridor-live until operator evidence is filed under `var/evidence/geos-99/offline/`.
