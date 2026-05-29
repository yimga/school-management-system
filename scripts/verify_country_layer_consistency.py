#!/usr/bin/env python3
"""Cross-check matrix education_pack_tier vs live resolve_country_pack()."""

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


def _expected_tier(alpha2: str) -> str:
    import django

    django.setup()
    from apps.siteconfig import _seed_country_localization as seed
    from apps.siteconfig.country_localization_service import resolve_country_pack

    if alpha2 in seed.COUNTRY_LOCALIZATION:
        return "tier1_native"
    pack = resolve_country_pack(alpha2)
    source = str(pack.get("_pack_source") or pack.get("pack_source") or "")
    if "regional" in source:
        return "tier1_regional_clone"
    return "generic_fallback"


def main() -> int:
    parser = argparse.ArgumentParser(description="Country layer consistency verifier")
    parser.add_argument("--mc-depth", action="store_true", help="Also check MC profile depth (Phase 3D)")
    parser.add_argument("--allow-skeleton", action="store_true", help="Skip deep checks when matrix is skeleton")
    args = parser.parse_args()

    if not MATRIX_PATH.is_file():
        print("FAIL: matrix missing", file=sys.stderr)
        return 1

    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = matrix.get("rows") or []
    failures: list[str] = []

    skeleton_mode = args.allow_skeleton or all(
        str(r.get("dissection_status") or "") == "skeleton" for r in rows
    )
    if skeleton_mode and not args.mc_depth:
        print("verify_country_layer_consistency: PASS (skeleton mode — tier sync deferred)")
        return 0

    for row in rows:
        iso = str(row.get("iso_alpha2") or "")
        matrix_tier = str(row.get("education_pack_tier") or "")
        live_tier = _expected_tier(iso)
        if matrix_tier != live_tier:
            failures.append(f"{iso}: matrix tier {matrix_tier} != live {live_tier}")
        if args.mc_depth:
            deep = row.get("deep_layers") or {}
            if row.get("research_tier") == "T1" and not deep.get("mc_profile"):
                failures.append(f"{iso}: T1 row missing mc_profile deep layer")

    if failures:
        print("verify_country_layer_consistency: FAIL", file=sys.stderr)
        for line in failures[:20]:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_country_layer_consistency: PASS ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
