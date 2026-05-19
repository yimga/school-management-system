# Companion siblings — extension, Tauri, Docker

This document is the SOT for the **three-way Companion family** that
implements customer-driven SIS migration extraction for the
RunMyCampus Migration Cloud. Each sibling lives at the **workspace
root** (not inside `beta/school-management-system/`) so that the legal
isolation between the customer-facing tool and the RunMyCampus
platform stays clean — they are separately-distributed software
products with distinct trust boundaries.

| Sibling | Path | Status (v3.34.0) |
|---------|------|---------|
| Browser extension | `companion-extension/` | Productionised in v3.32.0; per-vendor extractors land + harden across v3.31–v3.33 |
| Tauri desktop | `companion-tauri/` | **Honest scaffold** v0.1.0 (toolchain + crypto contract only) |
| Docker appliance | `companion-docker/` | **Honest scaffold** v0.1.0 (toolchain + FastAPI + crypto only) |

All three siblings share the same crypto wire format and seal against
the same server X25519 pubkey produced by
`apps/migration_cloud/services/companion_keypair.py`. The receiver is
the same Django view, `apps/migration_cloud/companion_receiver.py`.

## When to use which

The choice is driven by the customer's IT environment and the legacy
SIS surface, NOT by RunMyCampus preference. Operators should be able
to pick the path that fits their constraints.

### Use `companion-extension/` when…

- The customer's legacy SIS is **web-based** and the operator can
  reach it from a normal browser session (PowerSchool, Blackbaud,
  Veracross, Alma, browser-based FACTS/Skyward).
- The customer's workstation policy **allows browser extensions**
  (Chrome / Edge / Firefox).
- The operator is the customer's own admin signed into their own SIS
  account — Sony Betamax doctrine applies cleanly.

### Use `companion-tauri/` when…

- The customer's IT department **forbids browser extensions** but
  allows signed native apps.
- The customer's legacy SIS is a **thick-client Windows app** (older
  Skyward / FACTS deployments) where the data lives outside the
  browser.
- The customer needs an installer with **code signing + notarisation**
  for software-asset-management audits.
- The customer's workstation has narrow internet access and needs a
  per-device API token (Tauri's `seal_and_upload` IPC command makes
  the egress identity legible to network ops).

### Use `companion-docker/` when…

- The customer **cannot install** software on operator workstations
  (locked-down domain policy, no admin rights, audited endpoints) but
  **can** run a managed VM with a container runtime inside the DMZ.
- The legacy SIS exposes a **server-to-server API** (PowerSchool
  plugin endpoints, Blackbaud SKY API, Alma GraphQL) and can be hit
  with appliance-held credentials.
- The customer wants the migration to run **unattended** overnight
  with the appliance restarting on health-check failure.
- The migration scope is large enough that a single-operator-driven
  browser session would not finish in one sitting.

## Security tradeoffs

| Concern | Extension | Tauri | Docker |
|---------|-----------|-------|--------|
| Code trust boundary | Chrome extension sandbox | OS process + locked Tauri capabilities | Container with `cap_drop: [ALL]`, `no-new-privileges`, non-root user |
| Crypto runtime | libsodium-wrappers WASM (~200KB) | native libsodium via sodiumoxide | native libsodium via PyNaCl |
| Identity / auth | Customer's existing SIS browser session | Per-device API token (v3.35+) | Per-device API token + tenant host header |
| Credential storage | None (no credentials handled) | None (token in OS keychain in v3.35+) | Env var `RMC_API_TOKEN` at compose-up time |
| Egress visibility | Whatever the customer's browser does | Single named binary; clear in firewall logs | Single container; trivial to scope in DMZ firewall |
| Update path | Chrome Web Store / Edge Add-ons / AMO | Signed installers + Tauri updater | `docker pull` + restart |
| MAA enforcement | Popup gate before any extraction | `src/pages/maa-sign.html` gate before first upload | Server-side check via API token scope; per-launch confirmation in v3.35+ |
| Server-pubkey rotation | `key-rotation.ts::verifyServerKeyFingerprint` | `crypto.rs::constant_time_eq` against fetched fingerprint | `app/crypto.py::verify_fingerprint` (hmac.compare_digest) |
| Sealed-box wire format | identical | identical | identical |

## Operator workflow (end-to-end)

The shape is the same across all three siblings; the surface differs.

1. **Operator authenticates** with the RunMyCampus tenant in the
   control plane (`manager.runmycampus.com`).
2. **Operator signs the MAA** at the Companion's MAA-sign surface.
   The signed agreement is persisted server-side
   (`MigrationAuthorizationAgreement.signature_text_sha256`).
3. **Operator generates a per-device API token** at
   `/super/migration/tokens/` scoped to `bundles:write` +
   `artifacts:write`. (Extension uses the browser session instead.)
4. **Companion fetches the server X25519 pubkey** at
   `/super/migration/companion/server-pubkey/` and verifies the
   fingerprint against the operator-supplied expected value
   (rotation-detection defence).
5. **Companion extracts** canonical-bundle data from the source SIS.
   The extraction surface is per-sibling:
   - Extension: walks the operator's browser session.
   - Tauri: walks an authenticated thick-client session or driven API.
   - Docker: server-to-server API call against legacy SIS in DMZ.
6. **Companion seals** each bundle to the server pubkey using
   sealed-box (X25519 + XSalsa20-Poly1305). Plaintext NEVER crosses
   the network boundary.
7. **Companion uploads** the sealed ciphertext + integrity digest to
   `/super/migration/companion/upload/`.
8. **RunMyCampus operator decrypts** server-side via
   `CompanionDecryptHookView`, in memory only.

## v3.34.0 scaffold-honest scope

The Tauri and Docker scaffolds in this wave deliver:

- Directory shape (mirrors `companion-extension/` for cognitive parity).
- Manifest / `Cargo.toml` / `Dockerfile` that compiles in principle.
- Crypto contract (`sodiumoxide` in Rust, `PyNaCl` in Python) wire-
  format-identical to `companion-extension/src/lib/crypto.ts`.
- IPC / HTTP surface contracts (`fetch_pubkey` / `seal_and_upload` on
  Tauri; `GET /healthz` + `GET /pubkey` + `POST /upload` on Docker).
- A runnable hello-world flow that lets the operator exercise the
  crypto path end-to-end against a real RMC server.

What is **explicitly NOT in v3.34.0**:

- Per-vendor extractors for either sibling (PowerSchool / Blackbaud
  modules in `companion-docker/app/extractors/` are scaffolds that
  return sentinel records).
- Tauri code signing / notarisation / installer packaging.
- Docker image signing / SBOM emission.
- Per-device API token UX in Tauri (UI exists, persistence in
  OS keychain comes v3.35+).
- Strict forward semantics in `companion-docker/app/main.py::upload`
  (the forward is currently non-fatal so the appliance can be
  exercised on a developer's laptop without a live RMC server).

Every honest-stub function carries a comment naming exactly what's
missing — search `// honest-stub:` (Rust + TS) and `# honest-stub:`
(Python) to enumerate the deferred surface.

## Related docs

- `companion-extension/README.md` — the legal frame (Sony Betamax,
  CFAA, DMCA §1201, ToS-inducement) the whole family inherits.
- `docs/SECURITY_KEYS.md` — operator key-rotation runbook.
- `docs/DPA_TEMPLATE.md` + `docs/DSAR_RUNBOOK.md` — compliance
  posture the Companion family supports.
- `apps/migration_cloud/companion_receiver.py` — the receiving view.
- `apps/migration_cloud/services/companion_keypair.py` — the
  server-side keypair management every sibling seals against.
