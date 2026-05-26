#!/usr/bin/env python3
"""Fetch Redoc standalone bundle into static/vendor/redoc/ (one-time vendor step)."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = "https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"
OUT = Path(__file__).resolve().parent.parent / "static/vendor/redoc/redoc.standalone.js"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = urllib.request.urlopen(URL, timeout=120).read()
    except OSError as exc:
        print(f"fetch_vendor_redoc: FAIL {exc}", file=sys.stderr)
        return 1
    OUT.write_bytes(data)
    print(f"fetch_vendor_redoc: OK bytes={len(data)} path={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
