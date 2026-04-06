#!/usr/bin/env python3
"""
Fail if any template extends control_plane_base.html but is neither in
PHASE7_DASHBOARD_TEMPLATES nor EXEMPT_CONTROL_PLANE_TEMPLATES.

Operator hubs belong in Phase 7 + Phase 8; CRUD/shell/theme pages stay exempt.
See apps/dashboard/control_plane_hub_scan.py.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify control-plane hub registry drift."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _configure_root(base: Path) -> None:
    global ROOT
    ROOT = base
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _configure_root(_resolve_base(args.base))
    except ValueError as exc:
        print(f"verify_control_plane_hub_registry_drift: {exc}", file=sys.stderr)
        return 1

    from apps.dashboard.control_plane_hub_scan import (  # noqa: E402
        assert_control_plane_hub_registry_closed,
    )

    try:
        assert_control_plane_hub_registry_closed(ROOT / "templates")
    except AssertionError as e:
        print(f"verify_control_plane_hub_registry_drift: {e}", file=sys.stderr)
        return 1
    print("OK   control-plane hub registry closure (registered plus exempt covers all CP extends)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
