#!/usr/bin/env python3
"""Production or local smoke: GET homepage + lane routes.

Set PRODUCTION_BASE_URL for deployed host (e.g. https://runmycampus.com).
When unset, probes http://runmycampus.com:{MKT_LIGHTHOUSE_PORT} if Django responds.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PATHS = (
    "/",
    "/academics/",
    "/admissions/",
    "/finance/",
    "/pricing/",
)


def _probe(base: str, *, host_header: str) -> list[str]:
    failures: list[str] = []
    for path in PATHS:
        url = f"{base.rstrip('/')}{path}"
        req = urllib.request.Request(url, headers={"Host": host_header})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                code = resp.getcode()
                if code < 200 or code >= 400:
                    failures.append(f"{url} -> HTTP {code}")
        except urllib.error.HTTPError as exc:
            failures.append(f"{url} -> HTTP {exc.code}")
        except OSError as exc:
            failures.append(f"{url} -> {exc}")
    return failures


def _local_base() -> str | None:
    host = os.environ.get("MKT_LIGHTHOUSE_HOST", "runmycampus.com")
    port = os.environ.get("MKT_LIGHTHOUSE_PORT", "8000")
    health_url = f"http://127.0.0.1:{port}/"
    req = urllib.request.Request(health_url, headers={"Host": host})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status < 500:
                return f"http://127.0.0.1:{port}"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    return None


def main() -> int:
    base = (os.environ.get("PRODUCTION_BASE_URL") or "").strip().rstrip("/")
    mode = "production"
    if not base:
        base = _local_base() or ""
        mode = "local"
    if not base:
        print(
            "SKIP: verify_marketing_production_smoke — set PRODUCTION_BASE_URL or start Django on runmycampus.com:8000"
        )
        return 0

    host_header = os.environ.get("MKT_LIGHTHOUSE_HOST", "runmycampus.com")
    if mode == "production" and "://" in base:
        from urllib.parse import urlparse

        parsed = urlparse(base)
        if parsed.hostname:
            host_header = parsed.hostname
    failures = _probe(base, host_header=host_header)
    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1

    print(f"OK: verify_marketing_production_smoke ({mode}) — {len(PATHS)} paths on {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
