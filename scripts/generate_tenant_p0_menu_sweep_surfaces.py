#!/usr/bin/env python3
"""Generate Playwright P0 menu sweep surfaces from portal sidebar baselines (batch 1728 D1)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "tenant_p0_menu_sweep_surfaces.json"

ROLE_USER = {
    "TEACHER": "demo.teacher",
    "PARENT": "demo.parent",
    "STUDENT": "demo.student",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write JSON artifact")
    parser.add_argument("--check", action="store_true", help="Fail if artifact drift")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT))

    import django

    django.setup()

    from apps.siteconfig import portal_sidebar_items as psi

    surfaces: list[dict] = []

    def add(role_key: str, item_id: str, url_name: str, user: str) -> None:
        path = psi._baseline_reverse(url_name)
        if not path:
            return
        label = f"{role_key.lower()}-{item_id}"
        surfaces.append(
            {
                "label": label,
                "url": path,
                "user": user,
                "role": role_key,
                "url_name": url_name,
                "item_id": item_id,
            }
        )

    for role, specs in psi._BASELINE_BY_ROLE.items():
        user = ROLE_USER.get(role, f"demo.{role.lower()}")
        for item_id, _label, url_name, _icon, _section in specs:
            add(role, item_id, url_name, user)

    for item_id, _label, url_name, _icon, _section, _perm in psi._BASELINE_ADMIN:
        add("ADMIN", item_id, url_name, "demo.admin")

    payload = {
        "generated_by": "scripts/generate_tenant_p0_menu_sweep_surfaces.py",
        "schema_version": 1,
        "surface_count": len(surfaces),
        "surfaces": surfaces,
    }
    canonical = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    if args.write or not OUT.is_file():
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(canonical, encoding="utf-8")
        print(f"generate_tenant_p0_menu_sweep_surfaces: wrote {OUT} ({len(surfaces)} surfaces)")
        return 0

    if args.check:
        existing = OUT.read_text(encoding="utf-8")
        if existing != canonical:
            print("generate_tenant_p0_menu_sweep_surfaces: DRIFT — run with --write")
            return 1
        print("generate_tenant_p0_menu_sweep_surfaces: OK (no drift)")
        return 0

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
