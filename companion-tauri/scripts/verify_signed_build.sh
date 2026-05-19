#!/usr/bin/env bash
# RunMyCampus Companion (Tauri) — operator-side signed-build verifier.
#
# macOS:   spctl --assess --type install <path-to-dmg>
# Windows: signtool verify /pa <path-to-msi-or-exe>
#
# Exit 0 = trusted, 1 = untrusted / unknown platform / missing tool.
#
# Usage:
#   ./verify_signed_build.sh /path/to/RunMyCampusCompanion.dmg
#   ./verify_signed_build.sh /path/to/RunMyCampusCompanion.msi
#
# This script does NOT prove the binary is bug-free or
# vulnerability-free. It proves only that the binary was issued and
# signed by the RunMyCampus release pipeline against a trusted root
# (Apple Developer ID Application / DigiCert / Sectigo / etc.).

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <path-to-signed-installer>" >&2
  exit 1
fi

ARTIFACT="$1"

if [ ! -f "$ARTIFACT" ]; then
  echo "ERROR: artifact not found at '$ARTIFACT'" >&2
  exit 1
fi

UNAME_OUT="$(uname -s 2>/dev/null || echo unknown)"
EXT="${ARTIFACT##*.}"
EXT_LC="$(printf '%s' "$EXT" | tr '[:upper:]' '[:lower:]')"

case "$UNAME_OUT" in
  Darwin)
    if ! command -v spctl >/dev/null 2>&1; then
      echo "ERROR: spctl not found on PATH; macOS gatekeeper not available." >&2
      exit 1
    fi
    if [ "$EXT_LC" != "dmg" ] && [ "$EXT_LC" != "app" ] && [ "$EXT_LC" != "pkg" ]; then
      echo "WARN: extension '.$EXT' is unusual on macOS; proceeding anyway." >&2
    fi
    echo "Verifying notarization via spctl on '$ARTIFACT'"
    if spctl --assess --type install --verbose=4 "$ARTIFACT"; then
      echo "OK: '$ARTIFACT' is notarized + signed by trusted Apple Developer ID."
      exit 0
    else
      echo "FAIL: spctl rejected '$ARTIFACT'." >&2
      exit 1
    fi
    ;;
  MINGW*|MSYS*|CYGWIN*|Windows_NT)
    if ! command -v signtool >/dev/null 2>&1 && ! command -v signtool.exe >/dev/null 2>&1; then
      echo "ERROR: signtool not found on PATH; install Windows SDK or open a Developer PowerShell." >&2
      exit 1
    fi
    if [ "$EXT_LC" != "msi" ] && [ "$EXT_LC" != "exe" ]; then
      echo "WARN: extension '.$EXT' is unusual on Windows; proceeding anyway." >&2
    fi
    echo "Verifying Authenticode signature via signtool on '$ARTIFACT'"
    if signtool verify //pa "$ARTIFACT" 2>/dev/null || signtool verify /pa "$ARTIFACT"; then
      echo "OK: '$ARTIFACT' is Authenticode-signed by a trusted CA chain."
      exit 0
    else
      echo "FAIL: signtool rejected '$ARTIFACT'." >&2
      exit 1
    fi
    ;;
  *)
    echo "ERROR: unsupported platform '$UNAME_OUT' (need macOS or Windows)." >&2
    exit 1
    ;;
esac
