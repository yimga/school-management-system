#!/usr/bin/env python3
"""Fetch Chart.js 4.4.1 UMD bundle for django-unfold self-host gate."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"
OUT = Path(__file__).resolve().parent.parent / "static/unfold/js/chart/chart.js"
MIN_BYTES = 50_000


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = urllib.request.urlopen(URL, timeout=120).read()
    except OSError as exc:
        print(f"fetch_vendor_chart_js: FAIL {exc}", file=sys.stderr)
        return 1
    if len(data) < MIN_BYTES:
        print(
            f"fetch_vendor_chart_js: FAIL payload too small ({len(data)} bytes)",
            file=sys.stderr,
        )
        return 1
    OUT.write_bytes(data)
    print(f"fetch_vendor_chart_js: OK bytes={len(data)} path={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
