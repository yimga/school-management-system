#!/usr/bin/env python3
"""
Verify dual-dashboard topology: RBAC, middleware, migration, seed, shells, tests.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write docs/generated/dashboard_topology_audit.json",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run Django + vitest topology suites",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Repository root override (passed by verify_phases_3_11_gates.py); ignored when unset since REPO_ROOT is computed at import time.",
    )
    args = parser.parse_args()

    rbac = REPO_ROOT / "apps" / "schools" / "dashboard_rbac.py"
    registry = REPO_ROOT / "apps" / "schools" / "dashboard_topology_registry.py"
    middleware = REPO_ROOT / "apps" / "schools" / "middleware_dashboard_topology.py"
    migration = (
        REPO_ROOT
        / "apps"
        / "platform_runtime"
        / "migrations"
        / "0069_dashboard_topology_surface_tier.py"
    )
    seed_cmd = (
        REPO_ROOT
        / "apps"
        / "platform_runtime"
        / "management"
        / "commands"
        / "seed_dashboard_topology_links.py"
    )
    denied_tpl = REPO_ROOT / "templates" / "errors" / "dashboard_topology_denied.html"
    widget_tpl = REPO_ROOT / "templates" / "components" / "dashboard_widget_error_boundary.html"
    shell_css = REPO_ROOT / "static" / "css" / "dashboard-topology-shell.css"
    widget_js = REPO_ROOT / "static" / "js" / "rmc-dashboard-widget-boundary.js"

    for path in (
        rbac,
        registry,
        middleware,
        migration,
        seed_cmd,
        denied_tpl,
        widget_tpl,
        shell_css,
        widget_js,
    ):
        if not path.is_file():
            return _fail(f"missing {path.relative_to(REPO_ROOT)}")

    settings_text = (REPO_ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    if "DashboardTopologyRBACMiddleware" not in settings_text:
        return _fail("DashboardTopologyRBACMiddleware not wired in config/settings.py")
    if "dashboard_topology_context" not in settings_text:
        return _fail("dashboard_topology_context not in TEMPLATES context_processors")

    cp_skeleton = (REPO_ROOT / "templates" / "control_plane_skeleton.html").read_text(
        encoding="utf-8"
    )
    portal_base = (REPO_ROOT / "templates" / "portal_base.html").read_text(
        encoding="utf-8"
    )
    chrome_styles = (REPO_ROOT / "templates" / "partials" / "rmc_platform_chrome_styles.html").read_text(
        encoding="utf-8"
    )

    def _shell_has_topology_css(text: str) -> bool:
        if "dashboard-topology-shell.css" in text:
            return True
        return 'partials/rmc_platform_chrome_styles.html' in text and "dashboard-topology-shell.css" in chrome_styles

    for name, text in (("control_plane_skeleton", cp_skeleton), ("portal_base", portal_base)):
        if not _shell_has_topology_css(text):
            return _fail(f"{name} missing dashboard-topology-shell.css")
        if "rmc-dashboard-widget-boundary.js" not in text:
            return _fail(f"{name} missing rmc-dashboard-widget-boundary.js")

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.schools.dashboard_topology_registry import build_dashboard_topology_audit_matrix

    matrix = build_dashboard_topology_audit_matrix()
    if args.write:
        out = REPO_ROOT / "docs" / "generated" / "dashboard_topology_audit.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out}")

    if not matrix.get("ok"):
        return _fail(f"dashboard topology audit matrix not green: {matrix}")

    parity = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_super_admin_surface_parity.py")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if parity.returncode != 0:
        print(parity.stdout, parity.stderr)
        return _fail("super/admin surface parity verifier failed")

    if args.run_tests:
        django = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "run_sqlite_memory_tests.py"),
                "apps.schools.tests.test_dashboard_topology_integrity",
                "apps.platform_runtime.tests.test_dashboard_topology_seed",
            ],
            cwd=str(REPO_ROOT),
        )
        if django.returncode != 0:
            return _fail("Django dashboard topology tests failed")

        vitest = subprocess.run(
            ["npx", "vitest", "run", "tests/dashboard-topology-integrity.test.tsx"],
            cwd=str(REPO_ROOT),
            shell=True,
        )
        if vitest.returncode != 0:
            return _fail("vitest dashboard-topology-integrity failed")

    print("OK: dashboard topology integrity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
