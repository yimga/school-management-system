# Changelog — companion-tauri

All notable changes to the RunMyCampus Companion Tauri sibling are recorded
here. Format inspired by [Keep a Changelog](https://keepachangelog.com/).

## 3.39.0 — 2026-05-19

### Added
- Signed-release pipeline. Tag-only GitHub Actions workflows
  `.github/workflows/release-companion-tauri-{macos,windows}.yml` produce
  Apple-notarized `.dmg` (macOS) and Authenticode-signed `.msi`/`.exe`
  (Windows) on push of a `companion-tauri-v*` tag.
- Operator-side signature verifier at
  `companion-tauri/scripts/verify_signed_build.sh` (works on both macOS
  via `spctl` and Windows via `signtool verify /pa`).
- Pre-flight check `scripts/preflight_signed_release.py` that validates
  version-tag alignment + secret provisioning + CHANGELOG entry before a
  tag is pushed.

### Changed
- `Cargo.toml::version` aligned with this release.

### Security
- No signing key material is stored in the repository. Apple notarization
  uses the developer's `MACOS_CERT_P12_BASE64` + app-specific password
  secrets; Windows signing uses an EV/OV `.pfx` in the
  `WIN_CERT_PFX_BASE64` secret; both are provisioned in GitHub Actions
  org/repo secrets and never echoed in logs.

## 3.37.0 — 2026-05-19

### Added
- RMC platform handshake (`rmc_handshake.rs`) + canonical-CSV ingest
  (`canonical_csv.rs`) modules. Sealed-box upload via `sodiumoxide`.

## 3.34.0 — 2026-05-18

### Added
- Honest scaffold (Tauri 2.x + Rust + TS, sodiumoxide crypto contract).
- Initial directory shape mirroring `companion-extension/`.
