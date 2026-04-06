#!/usr/bin/env python3
"""
Gate: high–card-count Phase 7 dashboards must expose secondary density in a collapsible.

See apps.dashboard.dashboard_density_check.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"--base directory not found: {raw_base}")
    return base


def _load_density_violations(base: Path):
    module_path = base / "apps" / "dashboard" / "dashboard_density_check.py"
    if not module_path.is_file():
        raise ValueError(
            "apps/dashboard/dashboard_density_check.py not found under selected base"
        )
    spec = importlib.util.spec_from_file_location(
        "dashboard_density_check_for_phase8_verifier",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load dashboard density module from {module_path}")
    mod = importlib.util.module_from_spec(spec)
    base_s = str(base)
    added_sys_path = False
    if base_s not in sys.path:
        sys.path.insert(0, base_s)
        added_sys_path = True
    try:
        spec.loader.exec_module(mod)
    finally:
        if added_sys_path and sys.path and sys.path[0] == base_s:
            sys.path.pop(0)
    density_violations = getattr(mod, "density_violations", None)
    if density_violations is None:
        raise ValueError(
            "density_violations missing from apps/dashboard/dashboard_density_check.py"
        )
    return density_violations


def main(argv: list[str] | None = None) -> int:
    try:
        base = _resolve_base(parse_args(argv).base)
        density_violations = _load_density_violations(base)
    except ValueError as exc:
        print(f"verify_phase8_dashboard_density: {exc}", file=sys.stderr)
        return 1

    failures = density_violations(templates_root=base / "templates")
    if failures:
        print("FAIL Phase 8 dashboard density:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("OK   Phase 8 dashboard density (Phase 7 registry)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
