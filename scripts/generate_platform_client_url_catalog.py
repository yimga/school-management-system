#!/usr/bin/env python3
"""Emit / check platform_client_urls catalog keys from platform_surface_config SOT."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "platform_client_url_catalog.json"


def _catalog_keys() -> list[str]:
    import os
    import sys

    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from apps.siteconfig.platform_surface_config import _API_URL_CATALOG

    keys = [entry[0] for entry in _API_URL_CATALOG]
    keys.extend(
        (
            "dashboard_layout",
            "dashboard_available_widgets",
            "notification_read",
            "observability_incident_status",
        )
    )
    return sorted(set(keys))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    keys = _catalog_keys()
    payload = {
        "version": "v1",
        "keys": keys,
        "count": len(keys),
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)} ({len(keys)} keys)")
        return 0

    if args.check:
        if not OUT.is_file():
            print(f"FAIL: missing {OUT.relative_to(ROOT)}", file=sys.stderr)
            return 1
        on_disk = json.loads(OUT.read_text(encoding="utf-8"))
        if on_disk.get("keys") != keys:
            print("FAIL: platform_client_url_catalog.json stale — run --write", file=sys.stderr)
            return 1
        print("PLATFORM_CLIENT_URL_CATALOG_OK")
        return 0

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
