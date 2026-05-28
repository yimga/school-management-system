#!/usr/bin/env python3
"""Verify top-10 regional legacy shortcuts and canonical /<lang>/<cc>/ routes exist."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

TOP_TEN = ("US", "GB", "CA", "SA", "AE", "NG", "KE", "IN", "BR", "ID")


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from django.test import Client
    from django.urls import NoReverseMatch, reverse

    from apps.schools.marketing_region import (
        MARKETING_LEGACY_REGIONAL_SHORTCUTS,
        MARKETING_REGION_PROFILES,
        regional_landing_path,
    )

    errors: list[str] = []
    for cc in TOP_TEN:
        if cc not in MARKETING_REGION_PROFILES:
            errors.append(f"MARKETING_REGION_PROFILES missing {cc}")
        path = regional_landing_path(cc)
        if not path.startswith("/") or len(path) < 4:
            errors.append(f"bad canonical path for {cc}: {path}")

    legacy_countries = {row[1] for row in MARKETING_LEGACY_REGIONAL_SHORTCUTS}
    for cc in TOP_TEN:
        if cc not in legacy_countries:
            errors.append(f"legacy shortcut missing for {cc}")

    for prefix, country, lang, url_name in MARKETING_LEGACY_REGIONAL_SHORTCUTS:
        try:
            reverse(url_name)
        except NoReverseMatch:
            errors.append(f"url name not registered: {url_name} ({prefix}/ -> {country})")

    try:
        reverse("marketing_region", kwargs={"language_code": "en", "country_code": "ng"})
    except NoReverseMatch:
        errors.append("marketing_region canonical route missing")

    client = Client()
    host = os.environ.get("MARKETING_TEST_HOST", "runmycampus.com")
    for cc in TOP_TEN:
        path = regional_landing_path(cc)
        resp = client.get(
            path,
            HTTP_HOST=host,
            HTTP_X_FORWARDED_PROTO="https",
            secure=True,
        )
        if resp.status_code != 200:
            errors.append(f"canonical GET {path} -> {resp.status_code}")
        body = resp.content.decode("utf-8", errors="replace")
        if f'data-rmc-country="{cc}"' not in body:
            errors.append(f"canonical {path} missing data-rmc-country={cc}")

    if errors:
        print("verify_marketing_regional_routes: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_marketing_regional_routes: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
