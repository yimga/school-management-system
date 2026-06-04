#!/usr/bin/env bash
# Normalize integer env vars before Gunicorn import.
# Gunicorn reads WEB_CONCURRENCY at import time; dashboard paste errors like
# "2 ← optional headroom" must not crash the process.

_sanitize_nonneg_int() {
  local name="$1"
  local default="$2"
  local raw="${!name:-$default}"
  local cleaned
  cleaned="$(printf '%s' "$raw" | sed -E 's/^[[:space:]]*([0-9]+).*/\1/')"
  if [[ -z "$cleaned" ]]; then
    cleaned="$default"
  fi
  export "$name=$cleaned"
}

_sanitize_nonneg_int WEB_CONCURRENCY 1
_sanitize_nonneg_int GUNICORN_THREADS 4
_sanitize_nonneg_int GUNICORN_TIMEOUT 120
_sanitize_nonneg_int PORT 10000
_sanitize_nonneg_int SSE_THREAD_RESERVE 2
