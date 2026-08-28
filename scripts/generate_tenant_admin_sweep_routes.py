#!/usr/bin/env python3
"""Generate the complete tenant Django-admin route manifest for real-host sweeps."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

OUT = ROOT / "docs/generated/tenant_admin_sweep_routes.json"


def build_payload() -> dict:
    import django

    django.setup()
    from config.admin import tenant_admin_site

    rows: list[dict[str, object]] = [
        {"path": "/admin/", "archetype": "index", "sweep": True}
    ]
    apps: set[str] = set()
    for model in sorted(
        tenant_admin_site._registry,
        key=lambda value: (value._meta.app_label, value._meta.model_name),
    ):
        app = model._meta.app_label
        name = model._meta.model_name
        apps.add(app)
        base = f"/admin/{app}/{name}/"
        rows.append(
            {
                "path": base,
                "app": app,
                "model": name,
                "archetype": "changelist",
                "sweep": True,
            }
        )
        rows.append(
            {
                "path": f"{base}add/",
                "app": app,
                "model": name,
                "archetype": "add",
                "sweep": True,
            }
        )
    rows[1:1] = [
        {"path": f"/admin/{app}/", "app": app, "archetype": "app-index", "sweep": True}
        for app in sorted(apps)
    ]
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "adminSite": tenant_admin_site.name,
        "routeCount": len(rows),
        "routes": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUT.relative_to(ROOT)} ({payload['routeCount']} routes)")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
