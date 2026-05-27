#!/usr/bin/env python3
"""Preflight HTTP reachability for production marketing Playwright."""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://runmycampus.com")
    args = parser.parse_args()
    base = args.url.rstrip("/") + "/"
    try:
        with urllib.request.urlopen(base, timeout=20) as resp:  # noqa: S310
            code = resp.getcode()
    except urllib.error.URLError as exc:
        print(f"preflight_marketing_production_url: FAIL — {base} ({exc})", file=sys.stderr)
        return 1
    if code >= 400:
        print(f"preflight_marketing_production_url: FAIL — HTTP {code}", file=sys.stderr)
        return 1
    print(f"preflight_marketing_production_url: OK ({base} HTTP {code})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
