# Changelog — companion-docker

All notable changes to the RunMyCampus Companion Docker sibling are
recorded here. Format inspired by
[Keep a Changelog](https://keepachangelog.com/).

## 3.39.0 — 2026-05-19

### Added
- Signed-release pipeline. Tag-only GitHub Actions workflow
  `.github/workflows/release-companion-docker.yml` builds a multi-arch
  (linux/amd64,linux/arm64) image, pushes to GHCR, and signs the image
  digest with Sigstore Cosign keyless OIDC on push of a
  `companion-docker-v*` tag.
- Operator-side signature verifier
  `companion-docker/scripts/verify_signed_image.sh` (runs `cosign verify`
  against the expected RunMyCampus workflow identity).
- Pre-flight check `scripts/preflight_signed_release.py` integration.

### Changed
- `app/__init__.py::__version__` aligned with this release.

### Security
- Cosign keyless signing means there is no long-lived signing key to
  steal. The signature certificate is issued by Sigstore Fulcio for ~10
  minutes per workflow run, scoped to the workflow's OIDC identity
  (`https://github.com/runmycampus/...` at
  `https://token.actions.githubusercontent.com`).

## 3.37.0 — 2026-05-19

### Added
- RMC handshake (`app/rmc_handshake.py`) + canonical-CSV ingest
  (`app/canonical_csv.py`) + FastAPI `POST /ingest/csv` endpoint.

## 3.34.0 — 2026-05-18

### Added
- Honest scaffold (FastAPI inside python:3.12-slim, PyNaCl crypto
  contract, non-root container).
