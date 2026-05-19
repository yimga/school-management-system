#!/usr/bin/env bash
# v3.39.0 — test harness for `verify_signed_build.sh`.
#
# Asserts:
#  * non-existent input -> exit 1 with sensible error
#  * unknown platform (uname=Linux) -> exit 1
#  * missing argument -> exit 1
#
# This script does NOT attempt to mint a real signed installer (that
# would require Apple Developer ID or an Authenticode cert). It only
# verifies the negative-paths of the verifier.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$SCRIPT_DIR/verify_signed_build.sh"

if [ ! -x "$TARGET" ] && [ ! -f "$TARGET" ]; then
  echo "FAIL: verify_signed_build.sh missing at $TARGET" >&2
  exit 1
fi

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# Case 1: no args -> exit 1
if bash "$TARGET" 2>/dev/null; then
  fail "verifier accepted zero args"
fi

# Case 2: nonexistent file -> exit 1
TMP_MISSING="/tmp/rmc-companion-nonexistent-$$.dmg"
rm -f "$TMP_MISSING"
if bash "$TARGET" "$TMP_MISSING" 2>/dev/null; then
  fail "verifier accepted nonexistent file"
fi

# Case 3: real file but Linux platform (uname=Linux) -> exit 1
if [ "$(uname -s 2>/dev/null || echo unknown)" = "Linux" ]; then
  TMP_REAL="/tmp/rmc-companion-fake-$$.dmg"
  echo "not a real dmg" > "$TMP_REAL"
  set +e
  bash "$TARGET" "$TMP_REAL" >/dev/null 2>&1
  rc=$?
  set -e
  rm -f "$TMP_REAL"
  if [ "$rc" -eq 0 ]; then
    fail "verifier on Linux returned 0 for fake dmg"
  fi
fi

echo "OK: verify_signed_build.sh negative-path tests pass."
exit 0
