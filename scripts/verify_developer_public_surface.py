#!/usr/bin/env python3
"""Gate: developer section routes resolve and do not 500 on runmycampus.com (public_urls)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.test import Client
from django.test import override_settings
from django.urls import NoReverseMatch, reverse

PUBLIC_URLCONF = "config.public_urls"
HOST = "runmycampus.com"

# HTML surfaces (must not 500)
PAGE_PATHS = (
    "/developer/",
    "/developer/console/",
    "/developer-portal/",
    "/developer-portal/sdk/",
    "/developer-portal/sandbox/",
    "/developers/",
    "/developers/api/",
    "/developers/webhooks/",
    "/developers/integrations/",
    "/developers/sdk/",
    "/developers/app-building/",
    "/developers/api-docs/",
)

# Discovery APIs linked from hub (must not 500; 4xx without auth is OK)
API_PATHS = (
    "/api/v1/manifest.json",
    "/api/v2/manifest.json",
    "/api/v2/ping/",
    "/api/interop/",
    "/api/interop/oneroster/",
    "/marketplace/api/v1/catalog/",
)

REVERSE_NAMES = (
    "developer_hub",
    "developer_console",
    "developer_portal",
    "developer_sdk",
    "developer_sandbox",
    "developer_public_api_docs",
    "marketplace_dev:public_app_catalog_api",
    "marketplace_dev:publisher_signup",
)


def main() -> int:
    failures: list[str] = []
    for name in REVERSE_NAMES:
        try:
            path = reverse(name, urlconf=PUBLIC_URLCONF)
        except NoReverseMatch as exc:
            failures.append(f"reverse {name}: {exc}")
            continue
        if not path.startswith("/"):
            failures.append(f"reverse {name}: not absolute path {path!r}")

    client = Client(HTTP_HOST=HOST, raise_request_exception=False)
    with override_settings(ALLOWED_HOSTS=["*"]), __import__("unittest.mock", fromlist=["patch"]).patch.dict(
        os.environ,
        {"MULTI_TENANT_BASE_DOMAIN": HOST, "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
        clear=False,
    ):
        for path in PAGE_PATHS + API_PATHS:
            resp = client.get(path, secure=True)
            if resp.status_code >= 500:
                failures.append(f"GET {path}: HTTP {resp.status_code}")
                continue
            if path in PAGE_PATHS:
                body = resp.content.decode("utf-8", errors="replace")
                if "developer-section-nav" not in body:
                    failures.append(f"GET {path}: missing developer-section-nav")

    if failures:
        print("verify_developer_public_surface: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(
        f"verify_developer_public_surface: OK "
        f"({len(PAGE_PATHS)} pages, {len(API_PATHS)} APIs, {len(REVERSE_NAMES)} reverses)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
