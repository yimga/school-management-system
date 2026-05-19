# Reproducible Tauri Builds — RunMyCampus Companion

> v3.40.0 Migration Cloud platform-trust extension wave (Agent 2).
> Layered on top of v3.39.0 tag-only signed-release workflows.

This document describes how the macOS and Windows Tauri sibling builds
in `.github/workflows/release-companion-tauri-{macos,windows}.yml` are
made **byte-reproducible** for the unsigned executable / installer
body. The signature container intentionally differs across builds
(timestamp tokens, notarization staple, Authenticode counter-sign);
the *signed* body is identical at the byte level.

The goal is operator-auditable supply-chain trust: any third party who
can run our build inputs (same git commit, same toolchain, same env)
must be able to derive the same artifact hash and prove it matches
what was published to GitHub Releases under our Cosign + in-toto
attestation (see `scripts/verify_intoto_attestation.sh`).

---

## 1. SOURCE_DATE_EPOCH pinning

`SOURCE_DATE_EPOCH` is the canonical lever for build-time normalisation
(see https://reproducible-builds.org/specs/source-date-epoch/). The
Cargo + Tauri toolchains both honor it for embedded mtimes, archive
timestamps, and macOS resource-fork dates.

We derive `SOURCE_DATE_EPOCH` from the **tag commit** itself so the
value is bit-identical across reruns of the same tag:

```bash
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct "$RELEASE_TAG")
export SOURCE_DATE_EPOCH
```

Both workflows export this in their first build step. Do NOT use
`date +%s` (different per run) or the workflow `run_started_at`
(different per attempt).

## 2. Path prefix stripping via RUSTFLAGS

Rust embeds the absolute path of every source file into the resulting
binary's debug info section. On GitHub Actions runners the workspace
lives at `/home/runner/work/<repo>/<repo>` (Linux), `/Users/runner/work/...`
(macOS), or `D:\a\<repo>\<repo>` (Windows). Without normalisation these
paths leak the runner identity AND vary across re-runs of identical
inputs.

We strip them with `--remap-path-prefix`:

```bash
export RUSTFLAGS="--remap-path-prefix=${GITHUB_WORKSPACE}=/build --remap-path-prefix=${HOME}/.cargo=/cargo"
```

The `/build` and `/cargo` targets are placeholders any verifier can
reproduce locally; the actual on-disk path becomes irrelevant.

We also pin `CARGO_TARGET_<TRIPLE>_LINKER` to the system `cc` (Linux),
`clang` (macOS), or `link.exe` (Windows MSVC) explicitly so Cargo's
linker-selection heuristic (which inspects `$PATH` at build time)
cannot drift between runners.

## 3. Locked dependency resolution

Reproducible builds require frozen inputs. Three rules apply:

- **Cargo**: every `cargo` invocation in the release workflows passes
  `--locked --frozen`. `--locked` refuses to update `Cargo.lock`;
  `--frozen` additionally refuses to query the registry. `Cargo.lock`
  is checked in at `companion-tauri/src-tauri/Cargo.lock`.
- **Tauri CLI**: installed with `--locked` against a pinned version
  (`cargo install tauri-cli --version "^2.0" --locked`). Pinning to a
  narrow caret range is intentional — patch upgrades within Tauri 2.x
  remain byte-compatible per upstream guarantee; if a patch ever
  breaks reproducibility we pin to an exact version and file an
  upstream bug.
- **npm/pnpm**: front-end install passes `--frozen-lockfile` (pnpm)
  or `npm ci` (npm) — both refuse to mutate the lockfile. Lockfile
  is checked in at `companion-tauri/package-lock.json`.

## 4. tauri.conf.json signing-key indirection

`companion-tauri/src-tauri/tauri.conf.json` MUST NOT carry literal
key material. The `bundle.identifier` is a constant
(`com.runmycampus.companion`), but every secret-shaped field is
empty in source control and gets populated from environment variables
at build time:

```jsonc
{
  "bundle": {
    "identifier": "com.runmycampus.companion",
    "macOS": {
      "signingIdentity": null,        // populated from APPLE_SIGNING_IDENTITY env
      "providerShortName": null       // populated from APPLE_TEAM_ID env
    },
    "windows": {
      "certificateThumbprint": null,  // populated from WIN_CERT_THUMBPRINT env
      "timestampUrl": null            // populated from WIN_SIGN_TIMESTAMP_URL env
    }
  }
}
```

Reading literal keys from JSON in source control would (a) break
reproducibility (the file would change each rotation) and (b) leak
material to anyone reading the repo. The env-indirection means the
**source** is identical across builds; only the *signing operation*
applies key material, and the signature is stripped before the
reproducibility diff.

## 5. Comparison procedure

To verify reproducibility locally (or on a clean third-party runner):

```bash
# Clean run 1
git clone https://github.com/runmycampus/sms.git
cd sms
git checkout companion-tauri-v3.40.0
export SOURCE_DATE_EPOCH=$(git log -1 --format=%ct HEAD)
export RUSTFLAGS="--remap-path-prefix=$(pwd)=/build"
cd beta/school-management-system/companion-tauri
npm ci
cargo tauri build --target universal-apple-darwin   # or no --target for Windows
cp -r src-tauri/target/.../bundle /tmp/build-1
```

Do the same on a second clean runner to `/tmp/build-2`. Then:

```bash
# Strip signature containers before diffing.
#   macOS .dmg: extract the .app, then `codesign --remove-signature`
#   Windows .msi/.exe: `signtool remove /s`
diff -r /tmp/build-1/unsigned /tmp/build-2/unsigned
```

The expected output is empty. The `verify-reproducibility` job in
each release workflow does the same thing automatically by running
the build twice in fresh runners and comparing `sha256sum` of the
**unsigned** bundle body.

### Operator escape hatch

The `verify-reproducibility` job honors a `workflow_dispatch.inputs.
skip_reproducibility` input (default `"false"`). Setting it to
`"true"` short-circuits the double-build for incident response (e.g.,
emergency hotfix where a 30-minute redundant build is unacceptable).
This is NOT a default-on; the operator must explicitly opt out and
the dispatch shows up in the audit log.

## 6. Known reproducibility limits

These items still vary across builds and are EXCLUDED from the diff:

- **Signature containers**: Apple notarization staples a per-submission
  ticket; Authenticode counter-signs with a per-run timestamp token.
- **Build-id sections in binaries on Linux only** (not relevant here
  but documented for completeness).
- **macOS `.DS_Store`**: never include in artifacts; the build step
  filters them out before `productbuild` runs.

If a diff shows mismatches OUTSIDE these excluded sections, treat it
as a reproducibility regression and file an issue. The most common
real-world drift sources we have seen:

- Cargo registry not actually frozen (forgot `--frozen` somewhere)
- A `build.rs` reading `chrono::Utc::now()` or similar
- Tauri front-end bundler embedding a `Date.now()` watermark (fixed
  in upstream Tauri 2.1; older versions need a `vite.config.ts` patch)
- Dependency on the host's `/etc/localtime` (rare on CI but worth
  knowing about for on-prem rebuilds)

---

Last updated: 2026-05-19 (v3.40.0).
