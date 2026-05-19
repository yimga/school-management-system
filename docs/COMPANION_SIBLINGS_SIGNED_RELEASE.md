# Companion siblings — signed-release procedure (v3.39.0)

This document is the SOT for **producing trusted signed builds** of the
two operator-side Companion siblings:

| Sibling | Signed format | Trust anchor |
|---------|---------------|--------------|
| `companion-tauri/` (macOS) | Notarized `.dmg` (Apple Developer ID Application) | Apple notary service + stapled ticket |
| `companion-tauri/` (Windows) | Authenticode-signed `.msi` / `.exe` (EV or OV code-signing cert) | Trusted CA chain (DigiCert / Sectigo / GlobalSign / SSL.com) |
| `companion-docker/` (multi-arch image) | Sigstore Cosign keyless signature (OIDC) | Sigstore Fulcio cert + Rekor transparency log + GitHub Actions OIDC identity |

The `companion-extension/` sibling is signed separately through the
Chrome Web Store / Edge Add-ons / Firefox AMO publisher pipelines and
is out of scope for this document.

## What a signature DOES and DOES NOT prove

A signature on a build proves **provenance**:

- The binary / image was produced by the RunMyCampus release
  pipeline (i.e. a workflow run in this repository against a
  specific tag).
- The bytes have not been altered since the signature was applied.
- The publisher (RunMyCampus Inc.) holds a private signing key
  rooted in a public trust anchor (Apple, a Microsoft-trusted CA,
  or Sigstore's Fulcio).

A signature on a build **does NOT prove** any of:

- That the binary is free of bugs.
- That the binary is free of CVEs.
- That the binary's behavior matches its documentation.
- That the source code in this repo is faithfully reproduced in the
  binary. (Reproducible builds + a verified SBOM are a separate
  layer; we ship an SBOM with the Docker image and are working
  toward reproducible Tauri builds in a future wave.)

Operators verifying a binary should treat the signature as one
ingredient in a defense-in-depth posture, not as a complete trust
statement.

## Procurement

### Apple Developer ID Application (macOS Tauri)

- **Cost**: $99 USD / year (Apple Developer Program enrollment).
- **Where**: https://developer.apple.com/programs/enroll/
- **What to create**:
  1. Enroll the legal entity that publishes RunMyCampus (NOT a
     personal Apple ID).
  2. In the Apple Developer portal create a "Developer ID
     Application" certificate. Keep the private key inside Keychain
     Access on the signing workstation; export it as `.p12` with a
     strong password.
  3. Generate an app-specific password at
     https://appleid.apple.com (Security -> App-Specific Passwords).
     This is the password the notary service accepts; it is NOT the
     Apple ID login password.
  4. Note the 10-character Team ID from
     https://developer.apple.com/account (top right).
- **Outputs needed for CI**:
  - `MACOS_CERT_P12_BASE64`: `base64 -i developer-id.p12 | tr -d '\n'`
  - `MACOS_CERT_PASSWORD`: the .p12 export password.
  - `APPLE_ID`: the Apple ID email enrolled in the Developer Program.
  - `APPLE_TEAM_ID`: the 10-char team identifier.
  - `APPLE_APP_SPECIFIC_PASSWORD`: the notary password.

### EV / OV code-signing cert (Windows Tauri)

- **Cost**: ~$300-$700 USD / year (OV) or ~$400-$900 (EV).
- **Where**: DigiCert / Sectigo / GlobalSign / SSL.com.
- **Recommended**: an **EV** cert (Extended Validation). Microsoft
  SmartScreen warming requires either an EV cert (instant trust) or
  several weeks of telemetry on an OV-signed binary before the
  SmartScreen warning subsides.
- **Important constraint**: many EV CAs ship the cert pre-installed
  on a hardware HSM token (YubiKey or Safenet) and do NOT permit
  software-key export. Three workarounds:
  1. Use a cloud-HSM service (Azure Key Vault Premium, AWS CloudHSM,
     Google Cloud HSM). Pair with the
     [`AzureSignTool`](https://github.com/vcsjones/AzureSignTool) or
     `aws-kms-codesigner`. This document's Windows workflow uses
     local `signtool` for clarity; switching to AzureSignTool is a
     drop-in replacement for the signing step.
  2. Use a "non-EV OV" cert that issues as a software key (slower
     SmartScreen warm-up but works directly with `signtool`).
  3. Use SSL.com's "eSigner" managed signing service — they hold the
     EV key in their HSM and expose a remote signing API.
- **Outputs needed for CI** (software-key flow):
  - `WIN_CERT_PFX_BASE64`: `base64 -i code-signing.pfx | tr -d '\n'`
  - `WIN_CERT_PASSWORD`: the .pfx export password.
  - `WIN_SIGN_TIMESTAMP_URL`: RFC 3161 timestamp authority. Default
    `http://timestamp.digicert.com`.

### Sigstore Cosign keyless (Docker)

- **Cost**: $0. Sigstore Fulcio + Rekor are free public services.
- **Where**: Already enabled on any repo where the GitHub Actions
  workflow has `id-token: write` permission.
- **What to set up**: NOTHING in terms of secrets. The release
  workflow mints a short-lived OIDC token from GitHub, presents it
  to Fulcio, and Fulcio issues a signing certificate valid for ~10
  minutes. The signature is then published to the Rekor
  transparency log. Verifiers later check that the signing cert
  was issued to THIS workflow on THIS repo.
- **One-time setup**: ensure ghcr.io is enabled for the
  `runmycampus` GitHub organization (Settings -> Packages).

## Secret provisioning into GitHub Actions

For each secret listed above:

1. Open https://github.com/runmycampus/runmycampus/settings/secrets/actions
2. Click "New repository secret".
3. Paste the **exact** value. For base64-encoded `.p12` / `.pfx`
   files, paste the full base64 blob with no whitespace.
4. Confirm the secret name matches the workflow reference exactly
   (case-sensitive).

For organization-wide secrets (so multiple repos can share signing
material), provision at
https://github.com/organizations/runmycampus/settings/secrets/actions
instead and grant access only to this repo.

Never commit any of these values to git. The pre-flight script
`scripts/preflight_signed_release.py` will refuse to greenlight a
tag if any required secret is missing (when run with a `GITHUB_TOKEN`
in env that has `actions:read` scope).

## Tag procedure

1. Pick the new version (`X.Y.Z`).
2. Bump `companion-tauri/src-tauri/Cargo.toml` `version = "X.Y.Z"`
   AND/OR `companion-docker/app/__init__.py` `__version__ = "X.Y.Z"`.
3. Add a `CHANGELOG.md` entry (or update
   `docs/COMPANION_SIBLINGS_SIGNED_RELEASE.md`) describing the
   release.
4. Commit + push to `main`.
5. Run the pre-flight check:

   ```bash
   python scripts/preflight_signed_release.py companion-tauri-vX.Y.Z
   # and / or:
   python scripts/preflight_signed_release.py companion-docker-vX.Y.Z
   ```

   Exit 0 -> proceed. Exit 1 -> fix the reported blockers first.

6. Cut the tag locally and push it:

   ```bash
   git tag companion-tauri-vX.Y.Z
   git push origin companion-tauri-vX.Y.Z
   # and / or:
   git tag companion-docker-vX.Y.Z
   git push origin companion-docker-vX.Y.Z
   ```

7. Confirm the workflow fires in the Actions tab. The macOS, Windows,
   and Docker jobs are independent and may run in parallel.

8. If a release needs to be cancelled mid-flight, **delete the tag**
   on origin AND locally:

   ```bash
   git push origin :refs/tags/companion-tauri-vX.Y.Z
   git tag -d companion-tauri-vX.Y.Z
   ```

9. Manual dispatch is also available: go to Actions -> select the
   workflow -> "Run workflow" -> type **`publish`** in the confirm
   field. The workflow refuses any other input.

## Verifier-script usage (operator side)

After downloading a signed artifact from a GitHub Release (Tauri) or
pulling a tagged image from GHCR (Docker), customers and operators
can verify the signature locally.

### Tauri

```bash
# macOS:
companion-tauri/scripts/verify_signed_build.sh ~/Downloads/RunMyCampusCompanion-3.39.0-universal.dmg

# Windows (PowerShell or git-bash):
companion-tauri/scripts/verify_signed_build.sh "C:\Users\me\Downloads\RunMyCampusCompanion-3.39.0.msi"
```

Exit 0 means the OS trust store accepts the signature. Exit 1 means
the OS would warn the user at install time.

### Docker

```bash
# Bare tag, full ref computed automatically:
companion-docker/scripts/verify_signed_image.sh companion-docker-v3.39.0

# Or paste the full reference:
companion-docker/scripts/verify_signed_image.sh ghcr.io/runmycampus/companion-docker:companion-docker-v3.39.0
```

Exit 0 means the image was signed by the RunMyCampus release
workflow. Exit 1 means the image is unsigned, or the signature does
not chain back to a workflow run in `https://github.com/runmycampus/...`.

Operators in tight network environments may need to set:

- `RMC_COSIGN_IDENTITY_REGEX` — override the expected workflow
  identity regex (default `^https://github.com/runmycampus/.*`).
- `RMC_COSIGN_OIDC_ISSUER` — override the expected OIDC issuer
  (default `https://token.actions.githubusercontent.com`).

## Supply-chain trust model

The full chain a customer trusts when installing a signed Companion
appliance:

1. Customer trusts their **OS root trust store** (Apple, Microsoft,
   or the Sigstore root in `cosign` itself).
2. OS root trusts a **CA** (Apple, DigiCert, Sigstore Fulcio).
3. CA issued a **signing certificate** to RunMyCampus (or to a
   short-lived workflow identity, in Cosign's case).
4. Signing certificate was used to sign the **artifact digest**.
5. RunMyCampus controls the **release workflow** that invoked the
   signing tool, and the workflow only runs on **tag pushes** from
   the `runmycampus/runmycampus` repository.

Compromise of ANY link breaks the chain. The narrowest links to
defend per pillar:

- **Apple Developer ID**: protect the `.p12` + Apple ID
  app-specific password. Rotate the app-specific password quarterly.
  Apple will revoke and reissue the Developer ID cert on request if
  it appears compromised.
- **Windows EV / OV cert**: prefer a cloud HSM where the private
  key never leaves the HSM (Azure Key Vault Premium + AzureSignTool
  is the documented alternative). For software-key flows, scope
  `WIN_CERT_PFX_BASE64` to this repo only and rotate annually.
- **Cosign keyless**: there is no long-lived key to protect. The
  attack surface is instead the **workflow itself** — protect repo
  write access (branch protection, required reviewers, no force-push
  on `main`).

## Migration / deploy checklist (v3.39.0)

When operators want to ship the first signed build:

1. Procure the Apple Developer Program enrollment + Developer ID
   Application certificate (lead time: 24-48 hours for individual
   accounts, up to 2 weeks for D-U-N-S-verified organization
   accounts).
2. Procure the Windows EV or OV code-signing certificate (lead
   time: 1-5 business days depending on identity verification).
3. Provision the 8 Tauri secrets into GitHub Actions (see list
   above).
4. Push a test tag from a release branch (NOT main) — e.g.
   `companion-tauri-v3.39.0-rc1` — and confirm the workflow
   completes end-to-end. Cosign keyless and Apple notarization both
   require live network calls; rehearse before the real release.
5. Tag the real release: `companion-tauri-v3.39.0`.
6. After the release publishes, run the verifier scripts against
   the published artifacts to confirm operators get exit 0.

## Honest deferred

The following items are intentionally NOT in v3.39.0 and require a
follow-up wave:

- **Reproducible builds** for the Tauri appliance (so a customer
  can rebuild the .dmg byte-for-byte from source and confirm the
  hash matches the signed artifact). Tauri 2.x does not yet ship a
  reproducible-build flag; tracking the upstream issue.
- **In-toto attestations** layered on top of Cosign for the Docker
  image (statement = "this image was built from this commit by
  this workflow"). Cosign supports it but our workflow currently
  signs the digest only.
- **AzureSignTool migration** for the Windows workflow (cloud HSM
  flow). Documented above; the workflow itself currently uses
  local `signtool` with a software-key .pfx.
- **Chrome Web Store / Edge Add-ons / Firefox AMO publish pipeline**
  for `companion-extension/` (different trust story; out of scope
  for this document).
- **Customer-side Cosign installer bundle** so operators in
  air-gapped environments do not need to fetch cosign from the
  internet at verify time. Currently they must install cosign
  themselves.

## Related docs

- `docs/COMPANION_SIBLINGS.md` — extension vs Tauri vs Docker
  decision matrix.
- `docs/COMPANION_SIBLINGS_HANDSHAKE_AND_CSV_INGEST.md` — what each
  appliance actually does (RMC handshake + canonical-CSV ingest;
  NO programmatic SIS automation).
- `docs/SECURITY_KEYS.md` — operator key-rotation runbook for the
  RMC platform side (companion keypair, MAA signatures, webhook
  secrets). Distinct from this document, which covers build-time
  signing of the OPERATOR-side appliance.
- `scripts/preflight_signed_release.py` — pre-flight check this
  document drives.
