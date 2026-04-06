#!/usr/bin/env python3
"""
Gate: every registered full-page dashboard template must expose the Phase 7
decision surface contract (partial include, phase7_de context, or data attribute)
and the Phase 8 declaration tag (registry-driven strip).

See docs/PHASE_7_DASHBOARD_AND_ROLE_HOME_REWRITE.md — full dashboard registry.

Run (from repo root):
  python scripts/verify_phase7_dashboard_markers.py
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

_MARKER_RE = re.compile(
    r"(phase7_de|decision_engine_surface\.html|data-decision-engine\s*=)",
    re.MULTILINE,
)
_PHASE8_TAG_RE = re.compile(r"phase8_dashboard_declaration")

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT


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
        "phase7_dashboard_templates_for_marker_audit",
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
        print(f"verify_phase7_dashboard_markers: {exc}", file=sys.stderr)
        return 1

    templates_dir = base / "templates"
    failures: list[str] = []
    for rel in sorted(phase7_dashboard_templates):
        path = templates_dir / rel
        if not path.is_file():
            failures.append(f"{rel}: file missing")
            continue
        text = path.read_text(encoding="utf-8")
        if not _MARKER_RE.search(text):
            failures.append(
                f"{rel}: no Phase 7 marker "
                "(need phase7_de, decision_engine_surface.html include, or data-decision-engine=)"
            )
        if not _PHASE8_TAG_RE.search(text):
            failures.append(
                f"{rel}: missing Phase 8 tag "
                "{% phase8_dashboard_declaration \"…\" %}"
            )
    if failures:
        print("FAIL Phase 7/8 dashboard marker audit:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(
        f"OK   Phase 7/8 dashboard markers ({len(phase7_dashboard_templates)} templates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
