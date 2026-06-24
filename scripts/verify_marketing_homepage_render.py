#!/usr/bin/env python3
"""Compile + render marketing homepage and lane routes via Django test client."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.test import Client

HOST = os.environ.get("MKT_LIGHTHOUSE_HOST", "runmycampus.com")

PATHS = (
    "/",
    "/storefront/",
    "/academics/",
    "/admissions/",
    "/finance/",
    "/pricing/",
)

ROOT_MARKERS = (
    "data-mkt-day-role",
    "mkt-edt-globe__map--interactive",
    "marketing-gear2-home.css",
    "marketing-edge-layout.css",
    "mkt-edt-hero--edge",
    "marketing-page-personality.css",
    'data-mkt-personality="home"',
)

STOREFRONT_MARKERS = (
    "data-mkt-one-record-scroll",
    "panel-run",
    "data-mkt-speed-duel",
    "mkt-one-record-scroll.js",
)


def main() -> int:
    client = Client(HTTP_HOST=HOST)
    failures: list[str] = []

    for path in PATHS:
        response = client.get(path, follow=True)
        if response.status_code != 200:
            failures.append(f"{path} -> HTTP {response.status_code} (final {response.request.get('PATH_INFO', path)})")
            continue
        body = response.content.decode("utf-8", errors="replace")
        if path == "/" and not all(marker in body for marker in ROOT_MARKERS):
            failures.append(f"{path} -> missing gear2 homepage markers")
        if path == "/storefront/" and not all(marker in body for marker in STOREFRONT_MARKERS):
            failures.append(f"{path} -> missing One Record Scroll storefront markers")

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1

    print(f"OK: verify_marketing_homepage_render — {len(PATHS)} routes render HTTP 200")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
