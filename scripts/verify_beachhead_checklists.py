#!/usr/bin/env python3
"""Wedges 1–45: every operator checklist row must have a manager URL or tenant path_doc."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    os.chdir(REPO)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
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
        print("verify_beachhead_checklists FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(
        "verify_beachhead_checklists: PASS (wedges "
        f"{', '.join(str(w) for w in beachhead_wedge_ids())})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
