#!/usr/bin/env python3
"""Wedges 1–45: every operator checklist row must have a manager URL or tenant path_doc.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify beachhead checklist coverage."
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
    global REPO
    REPO = base
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _configure_root(_resolve_base(args.base))
    except ValueError as exc:
        print(f"verify_beachhead_checklists: {exc}", file=sys.stderr)
        return 1

    os.chdir(REPO)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from django.test.utils import override_settings

    from apps.platform_runtime.beachhead_operator_checklists import (
        beachhead_wedge_ids,
        build_resolved_beachhead_checklist,
    )
    from apps.schools.super_views_wedge import _safe_reverse

    errors: list[str] = []
    with override_settings(ROOT_URLCONF="config.manager_urls"):
        for wid in beachhead_wedge_ids():
            rows = build_resolved_beachhead_checklist(wid, _safe_reverse)
            if len(rows) < 4:
                errors.append(f"Wedge {wid}: expected >= 4 checklist rows, got {len(rows)}")
            for i, row in enumerate(rows):
                if not (row.get("url") or row.get("path_doc")):
                    errors.append(
                        f"Wedge {wid} row {i} ({row.get('label')}): missing url and path_doc"
                    )

    if errors:
        print("verify_beachhead_checklists:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(
        "verify_beachhead_checklists: PASS (wedges "
        f"{', '.join(str(w) for w in beachhead_wedge_ids())})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
