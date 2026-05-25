#!/usr/bin/env python3
"""Manager complete sidebar — CP + admin catalog one tree (batch 1500)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(rel: str, *needles: str) -> bool:
    path = ROOT / rel
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return all(n in text for n in needles)


def main() -> int:
    checks = [
        ("complete-partial", (ROOT / "templates/partials/manager_complete_sidebar_nav.html").is_file()),
        ("admin-complete-sidebar", _ok(
            "templates/partials/manager_platform_admin_sidebar.html",
            "manager_complete_sidebar_nav.html",
            "data-rmc-complete-sidebar",
        )),
        ("cp-complete-sidebar", _ok(
            "templates/partials/control_plane_sidebar.html",
            "manager_complete_sidebar_nav.html",
            "data-rmc-complete-sidebar",
        )),
        ("context-complete-nav", _ok(
            "apps/siteconfig/context_processors.py",
            "MANAGER_COMPLETE_SIDEBAR_NAV",
            "build_manager_complete_sidebar_groups",
        )),
        ("module-complete-builder", _ok(
            "apps/schools/manager_nav_convergence.py",
            "build_manager_complete_sidebar_groups",
            "build_manager_catalog_nav_groups",
        )),
    ]
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory

    from apps.schools.manager_nav_convergence import build_manager_complete_sidebar_groups

    request = RequestFactory().get("/super/")
    request.urlconf = "config.manager_urls"
    request.user = get_user_model()(is_superuser=True, username="nav_complete")
    complete = build_manager_complete_sidebar_groups(request)
    checks.append(("complete-nav-min-groups", len(complete) >= 4))
    catalog = [g for g in complete if str(g.get("group_id", "")).startswith("catalog_")]
    checks.append(("catalog-groups-present", len(catalog) >= 1))

    req_admin = RequestFactory().get("/admin/")
    req_admin.urlconf = "config.manager_urls"
    req_admin.user = request.user
    admin_complete = build_manager_complete_sidebar_groups(req_admin)
    admin_group_ids = [g.get("group_id") for g in admin_complete]
    super_group_ids = [g.get("group_id") for g in complete]
    checks.append(("admin-super-tree-parity", admin_group_ids == super_group_ids))

    failed = [name for name, ok in checks if not ok]
    if failed:
        print(f"verify_manager_nav_convergence: FAIL ({len(failed)})", file=sys.stderr)
        for name in failed:
            print(f"  - {name}", file=sys.stderr)
        return 1
    print(
        "verify_manager_nav_convergence: MANAGER_COMPLETE_SIDEBAR_PASS "
        f"({len(checks)} checks; {len(complete)} groups; {len(catalog)} catalog sections)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
