#!/usr/bin/env bash
# Fail if .env or .env.local (etc.) are tracked by git (prevents committing secrets).
# Local copies on disk are allowed; only committed/tracked files trigger failure.
# Allow .env.example. Use in CI or pre-commit.
set -e
tracked=$(git ls-files .env .env.local .env.development.local .env.test.local .env.production.local 2>/dev/null || true)
if [ -n "$tracked" ]; then
  echo "ERROR: These env files must not be committed. Remove from the repo: git rm --cached <file>"
  echo "$tracked"
  exit 1
fi
echo "OK: No forbidden env files tracked in git."
