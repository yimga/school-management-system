#!/usr/bin/env bash
# RunMyCampus Companion (Docker) — operator-side Cosign signature verifier.
#
# Verifies that a published image at
#   ghcr.io/runmycampus/companion-docker:<TAG>
# was signed by the RunMyCampus GitHub Actions release workflow via
# Sigstore keyless OIDC.
#
# Exit 0 = signature verified, 1 = untrusted / missing tool.
#
# Usage:
#   ./verify_signed_image.sh companion-docker-v3.39.0
#   ./verify_signed_image.sh ghcr.io/runmycampus/companion-docker:companion-docker-v3.39.0
#
# This script does NOT prove the image is free of bugs or CVEs. It
# proves only that the image digest was signed by a short-lived cert
# issued by Sigstore Fulcio to a workflow run identifying as
# `https://github.com/runmycampus/...` over the GitHub Actions OIDC
# issuer.

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <tag-or-full-ref>" >&2
  exit 1
fi

INPUT="$1"

if ! command -v cosign >/dev/null 2>&1; then
  echo "ERROR: cosign not found on PATH; install from https://docs.sigstore.dev/cosign/installation/" >&2
  exit 1
fi

# Normalize: accept bare tag OR full ref.
case "$INPUT" in
  ghcr.io/*)
    REF="$INPUT"
    ;;
  *)
    REF="ghcr.io/runmycampus/companion-docker:${INPUT}"
    ;;
esac

IDENTITY_REGEX="${RMC_COSIGN_IDENTITY_REGEX:-^https://github.com/runmycampus/.*}"
OIDC_ISSUER="${RMC_COSIGN_OIDC_ISSUER:-https://token.actions.githubusercontent.com}"

echo "Verifying Cosign signature on '$REF'"
echo "  certificate-identity-regexp: $IDENTITY_REGEX"
echo "  certificate-oidc-issuer:     $OIDC_ISSUER"

if cosign verify \
  --certificate-identity-regexp "$IDENTITY_REGEX" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$REF" >/dev/null; then
  echo "OK: '$REF' is signed by RunMyCampus GitHub Actions release workflow."
  exit 0
else
  echo "FAIL: cosign verify rejected '$REF'." >&2
  exit 1
fi
