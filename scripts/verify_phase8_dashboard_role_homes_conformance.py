#!/usr/bin/env python3
"""
Phase 8 gate (narrow): dashboards + role homes structural conformance.

Does not duplicate Phase 8 density checks — use ``verify_phase8_dashboard_density.py`` or
``apps/dashboard/tests/test_phase8_dashboard_density.py`` for collapsible-density law.

Run (from repo root):
  python scripts/verify_phase8_dashboard_role_homes_conformance.py
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root to inspect (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"--base directory not found: {raw_base}")
    return base


def _load_phase7_dashboard_templates(base: Path) -> tuple[str, ...]:
    module_path = base / "apps" / "dashboard" / "phase7_dashboard_templates.py"
    if not module_path.is_file():
        raise ValueError(
            "apps/dashboard/phase7_dashboard_templates.py not found under selected base"
        )
    spec = importlib.util.spec_from_file_location(
        "phase7_dashboard_templates_for_role_home_conformance",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load dashboard template registry from {module_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    templates = getattr(mod, "PHASE7_DASHBOARD_TEMPLATES", None)
    if templates is None:
        raise ValueError(
            "PHASE7_DASHBOARD_TEMPLATES missing from apps/dashboard/phase7_dashboard_templates.py"
        )
    return tuple(templates)


def main(argv: list[str] | None = None) -> int:
    try:
        base = _resolve_base(parse_args(argv).base)
        phase7_dashboard_templates = _load_phase7_dashboard_templates(base)
    except ValueError as exc:
        print(f"verify_phase8_dashboard_role_homes_conformance: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    super_dash = base / "templates" / "schools" / "super_dashboard.html"
    decision_surface = base / "templates" / "components" / "decision_engine_surface.html"
    role_home_tests = base / "apps" / "dashboard" / "tests" / "test_role_home_engine.py"
    role_home_engine = base / "apps" / "dashboard" / "role_home_engine.py"

    for p in (super_dash, decision_surface, role_home_tests, role_home_engine):
        if not p.is_file():
            errors.append(f"Missing required file: {p.relative_to(base).as_posix()}")

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

    if "schools/super_dashboard.html" not in phase7_dashboard_templates:
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
    raise SystemExit(main(None))
