#!/usr/bin/env python3
"""
Django-client smoke: sample platform admin changelists from sweep routes render
steering strip + scroll host (P3 fallback when Playwright server unavailable).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

ROUTES_JSON = ROOT / "docs/generated/control_plane_sweep_routes.json"
MAX_ROUTES = int(os.environ.get("ADMIN_RENDER_SAMPLE_MAX", "24"))
HOST = os.environ.get("VERIFY_ADMIN_RENDER_HOST", "manager.runmycampus.com")


def main() -> int:
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.test import Client

    if not ROUTES_JSON.is_file():
        print(f"FAIL: missing {ROUTES_JSON}", file=sys.stderr)
        return 1

    data = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
    paths = [
        r["path"]
        for r in data.get("routes", [])
        if r.get("tier") == "admin_changelist" and r.get("sweep")
    ][:MAX_ROUTES]
    if not paths:
        print("FAIL: no admin_changelist routes in sweep JSON", file=sys.stderr)
        return 1

    User = get_user_model()
    user = User.objects.filter(is_superuser=True, is_staff=True).first()
    if not user:
        print("FAIL: no superuser for admin render smoke", file=sys.stderr)
        return 1

    client = Client(HTTP_HOST=HOST)
    client.force_login(user)

    failures: list[str] = []
    for path in paths:
        try:
            response = client.get(path, follow=True)
        except Exception as exc:
            failures.append(f"{path}: request error {exc}")
            continue
        if response.status_code >= 400:
            failures.append(f"{path}: HTTP {response.status_code}")
            continue
        html = response.content.decode("utf-8", errors="replace")
        if "data-rmc-admin-steering-strip" not in html:
            failures.append(f"{path}: missing steering strip marker")
        if "cp-main-content" not in html and "admin-manager-shell" not in html:
            failures.append(f"{path}: missing manager admin shell markers")

    if failures:
        for msg in failures[:20]:
            print(f"FAIL: {msg}", file=sys.stderr)
        if len(failures) > 20:
            print(f"... and {len(failures) - 20} more", file=sys.stderr)
        return 1

    print(
        f"verify_admin_changelist_render_contract: OK ({len(paths)} admin changelists)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
