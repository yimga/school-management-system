#!/usr/bin/env python3
"""Admin backoffice ↔ control-plane help nav bridge (batch 1486)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ok(rel: str, *needles: str) -> bool:
    path = ROOT / rel
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return all(n in text for n in needles)


def main() -> int:
    checks = [
        (
            "admin-manager-help",
            _ok(
                "templates/admin/sidebar_v3_body.html",
                "manager_help_center",
                "Libraries & help",
            ),
        ),
        (
            "admin-tenant-unified-help",
            _ok(
                "templates/admin/sidebar_v3_body.html",
                "feedback:help_center",
                "Knowledge Base",
            ),
        ),
        (
            "admin-control-plane-bridge",
            _ok("templates/admin/sidebar_v3_body.html", "super:dashboard", "Control plane"),
        ),
        (
            "tenant-portal-sidebar-help",
            _ok(
                "apps/siteconfig/portal_sidebar_items.py",
                '"id": "help_center"',
                "feedback:help_center",
            ),
        ),
        (
            "404-host-aware-help",
            _ok("templates/errors/404.html", "manager_help_center", "feedback:help_center"),
        ),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        print(f"verify_admin_super_help_nav_bridge: FAIL ({len(failed)})", file=sys.stderr)
        for name in failed:
            print(f"  - {name}", file=sys.stderr)
        return 1
    print(
        "verify_admin_super_help_nav_bridge: ADMIN_SUPER_HELP_NAV_BRIDGE_PASS "
        f"({len(checks)} checks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
