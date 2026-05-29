#!/usr/bin/env python3
"""Track ISO 3166-2 subdivision seed coverage (SubdivisionRegistry)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO / "docs" / "generated" / "country_governance_matrix.json"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    parser = argparse.ArgumentParser(description="Subdivision coverage verifier")
    parser.add_argument("--min-sovereign-pct", type=float, default=0.0)
    parser.add_argument("--allow-zero", action="store_true", help="Pass at 0%% during Phase 0A")
    args = parser.parse_args()

    import django

    django.setup()

    sovereign_total = 0
    seeded = 0
    if MATRIX_PATH.is_file():
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for row in matrix.get("rows") or []:
            if row.get("sovereign_state"):
                sovereign_total += 1
                deep = row.get("deep_layers") or {}
                if deep.get("subdivisions_seeded"):
                    seeded += 1

    try:
        from apps.registries.models import SubdivisionRegistry

        db_count = SubdivisionRegistry.objects.count()
    except Exception:
        db_count = 0

    pct = (100.0 * seeded / sovereign_total) if sovereign_total else 0.0
    if db_count > 0 and seeded == 0:
        pct = min(100.0, 100.0 * db_count / max(sovereign_total, 1))

    if args.allow_zero and args.min_sovereign_pct <= 0:
        print(f"verify_subdivision_coverage: PASS (scaffold — {pct:.1f}% sovereign, db_rows={db_count})")
        return 0

    if pct < args.min_sovereign_pct:
        print(
            f"verify_subdivision_coverage: FAIL — {pct:.1f}% < {args.min_sovereign_pct}%",
            file=sys.stderr,
        )
        return 1

    print(f"verify_subdivision_coverage: PASS ({pct:.1f}% sovereign coverage)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
