#!/usr/bin/env python3
"""
Agent 7 — Magic UX gate (fast path): audit JSON + no-DB Django tests + shell/design verifiers.

Does not run full HTTP integration tests (those need a migrated test DB). Use:

  DJANGO_TEST_DB_FILE=.django_test_dbs/magic_ux.sqlite3 \\
    python manage.py test \\
      apps.platform_runtime.tests.test_magic_ux_surfaces \\
      apps.platform_runtime.tests.test_magic_ux_measurement_and_literals \\
      apps.siteconfig.tests.test_compliance_exports.ComplianceExportsSlice5Tests.test_magic_ux_strict_wraps_secondary_links_in_more_actions \\
      apps.marketplace.tests.test_tenant_catalog_magic_ux_strict \\
      apps.portal.tests.test_magic_ux_portal_surfaces_http \\
      --noinput -v 1

after the DB is created once (or with --keepdb).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str]) -> int:
    print("+", " ".join(argv))
    r = subprocess.run(argv, cwd=ROOT)
    return r.returncode


def main() -> int:
    py = sys.executable
    steps = [
        [py, "scripts/generate_magic_ux_screen_audit.py"],
        [
            py,
            "manage.py",
            "test",
            "apps.platform_runtime.tests.test_magic_ux_closure_slice",
            "apps.platform_runtime.tests.test_magic_ux_surfaces",
            "apps.platform_runtime.tests.test_magic_ux_measurement_and_literals",
            "--noinput",
            "-v",
            "1",
        ],
        [py, "scripts/verify_design_system_phase2.py"],
        [py, "scripts/verify_shell_surface_inventory.py"],
        [py, "scripts/verify_phase2_authenticated_shell_conformance.py"],
        [py, "scripts/audit_luxury_ui_surface.py"],
        [py, "scripts/audit_regional_ui_surface.py"],
    ]
    for s in steps:
        rc = run(s)
        if rc != 0:
            return rc
    print("verify_magic_ux_agent7_gate: PASS (fast bundle)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
