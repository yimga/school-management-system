#!/usr/bin/env python3
"""
Gate: apps with real migrations must appear in SHARED_APPS or TENANT_APPS when
schema-per-tenant mode is active (Render pre-deploy uses migrate_schemas).

Without this, new apps can land in base INSTALLED_APPS but be dropped when
USE_DJANGO_TENANTS=1 rebuilds INSTALLED_APPS — migrations never apply and
management commands under those apps are not discoverable.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "config" / "settings.py"

# Proxy-only migration apps (CreateModel proxy=True only) — optional in SHARED.
_PROXY_ONLY_APPS: frozenset[str] = frozenset(
    {
        "apps.integrations_marketplace",
        "apps.plans_entitlements",
        "apps.policies_rules",
    }
)


def _norm_app(entry: str) -> str:
    if not entry.startswith("apps."):
        return entry
    parts = entry.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return entry


def _parse_app_list(block: str) -> set[str]:
    return {_norm_app(m) for m in re.findall(r'"([^"]+)"', block) if m.startswith("apps.")}


def _apps_with_migrations() -> set[str]:
    found: set[str] = set()
    for mig in ROOT.glob("apps/*/migrations/0*.py"):
        app_root = f"apps.{mig.parent.parent.name}"
        found.add(app_root)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-proxy",
        action="store_true",
        help="Also require proxy-only bounded-context apps in SHARED/TENANT lists.",
    )
    args = parser.parse_args()

    text = SETTINGS.read_text(encoding="utf-8")
    if "SHARED_APPS = [" not in text:
        print("verify_tenant_schema_app_registration: SKIP (no SHARED_APPS block)")
        return 0

    shared_block = text.split("SHARED_APPS = [", 1)[1].split("]", 1)[0]
    tenant_block = text.split("TENANT_APPS = [", 1)[1].split("]", 1)[0]
    registered = _parse_app_list(shared_block) | _parse_app_list(tenant_block)

    required = _apps_with_migrations()
    if not args.include_proxy:
        required -= _PROXY_ONLY_APPS

    missing = sorted(required - registered)
    if missing:
        print(
            "verify_tenant_schema_app_registration: FAIL — add to SHARED_APPS or TENANT_APPS:",
            file=sys.stderr,
        )
        for app in missing:
            print(f"  - {app}", file=sys.stderr)
        return 1

    print(
        f"verify_tenant_schema_app_registration: OK ({len(required)} apps with migrations registered)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
