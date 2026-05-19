# RunMyCampus Companion (Tauri) — v3.37.0

Desktop appliance for the Migration Cloud handshake + canonical-CSV
ingest. See `docs/COMPANION_SIBLINGS_HANDSHAKE_AND_CSV_INGEST.md` at
the repo root for the full architectural-boundary contract.

## Build (developer)

```bash
cd companion-tauri
npm install
cd src-tauri && cargo test    # 10 tests pass (handshake + csv + crypto)
cd .. && npm run tauri dev    # launches the 4-step wizard window
```

## What this appliance does NOT do

It does NOT log into PowerSchool / Blackbaud / Veracross / Alma / FACTS
/ Skyward. Programmatic vendor login lives in `companion-extension/`
where the operator's own authenticated browser tab is the security
boundary.
