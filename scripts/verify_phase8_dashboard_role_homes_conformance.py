#!/usr/bin/env python3
"""
Phase 8 gate (narrow): dashboards + role homes structural conformance.

Does not duplicate Phase 8 density checks — use ``verify_phase8_dashboard_density.py`` or
``apps/dashboard/tests/test_phase8_dashboard_density.py`` for collapsible-density law.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []

    super_dash = ROOT / "templates" / "schools" / "super_dashboard.html"
    decision_surface = ROOT / "templates" / "components" / "decision_engine_surface.html"
    role_home_tests = ROOT / "apps" / "dashboard" / "tests" / "test_role_home_engine.py"
    role_home_engine = ROOT / "apps" / "dashboard" / "role_home_engine.py"

    for p in (super_dash, decision_surface, role_home_tests, role_home_engine):
        if not p.is_file():
            errors.append(f"Missing required file: {p.relative_to(ROOT).as_posix()}")

    if errors:
        print("verify_phase8_dashboard_role_homes_conformance: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    super_text = _read(super_dash)
    for needle in (
        'extends "control_plane_base.html"',
        'data-page-archetype="role-home"',
        'data-decision-engine="surface"',
        'phase8_dashboard_declaration',
    ):
        if needle not in super_text:
            errors.append(
                f"templates/schools/super_dashboard.html missing contract token: {needle!r}"
            )

    de_text = _read(decision_surface)
    for needle in (
        'data-decision-engine="surface"',
        'data-decision-zone="headline"',
        'data-decision-zone="urgent-queue"',
        'data-decision-zone="next-best-actions"',
        'data-decision-zone="activity-trend"',
    ):
        if needle not in de_text:
            errors.append(
                f"templates/components/decision_engine_surface.html missing contract token: {needle!r}"
            )

    test_text = _read(role_home_tests)
    for needle in (
        "from apps.dashboard.role_home_engine import",
        "resolve_role_home",
        "class RoleHomeEngineTests",
    ):
        if needle not in test_text:
            errors.append(
                f"apps/dashboard/tests/test_role_home_engine.py missing contract token: {needle!r}"
            )

    from apps.dashboard.phase7_dashboard_templates import PHASE7_DASHBOARD_TEMPLATES

    if "schools/super_dashboard.html" not in PHASE7_DASHBOARD_TEMPLATES:
        errors.append(
            "PHASE7_DASHBOARD_TEMPLATES must include schools/super_dashboard.html"
        )

    if errors:
        print("verify_phase8_dashboard_role_homes_conformance: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_phase8_dashboard_role_homes_conformance: PASS "
        "(role-home + decision-surface contracts; density gate separate)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
