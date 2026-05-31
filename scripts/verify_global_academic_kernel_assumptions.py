#!/usr/bin/env python3
"""Global academic kernel assumptions — pack/matrix alignment + policy discipline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO / "docs" / "generated" / "country_governance_matrix.json"
OUT_PATH = REPO / "docs" / "generated" / "global_academic_kernel_audit.json"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def _pack_tier_from_source(source: str) -> str:
    if source.startswith("country:"):
        return "tier1_native"
    if source.startswith("regional:") and source != "regional:generic":
        return "tier1_regional_clone"
    return "generic_fallback"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    import django

    django.setup()

    from apps.governance.academic_pack_bridge import audit_pack_matrix_alignment
    from apps.siteconfig.country_localization_service import resolve_country_pack

    failures: list[str] = []
    tier_counts = {"tier1_native": 0, "tier1_regional_clone": 0, "generic_fallback": 0}
    missing_keys: list[str] = []

    if MATRIX_PATH.is_file():
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        rows = matrix.get("rows") or []
        failures.extend(audit_pack_matrix_alignment(rows))
        for row in rows:
            iso = str(row.get("iso_alpha2") or "")
            if not iso:
                continue
            pack = resolve_country_pack(iso)
            source = str(pack.get("_source") or "")
            tier_counts[_pack_tier_from_source(source)] += 1
            for key in ("school_types", "education_levels", "terminology"):
                if not pack.get(key):
                    missing_keys.append(f"{iso}: missing {key}")
    else:
        failures.append("country_governance_matrix.json missing")

    failures.extend(missing_keys[:50])
    if len(missing_keys) > 50:
        failures.append(f"... and {len(missing_keys) - 50} more missing pack keys")

    payload = {
        "verdict": "GLOBAL_ACADEMIC_KERNEL_PASS" if not failures else "GLOBAL_ACADEMIC_KERNEL_FAIL",
        "finding_count": len(failures),
        "tier_counts": tier_counts,
        "findings": failures[:100],
    }
    if args.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if failures and args.strict:
        print(f"verify_global_academic_kernel_assumptions: FAIL ({len(failures)})", file=sys.stderr)
        for line in failures[:15]:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(
        f"verify_global_academic_kernel_assumptions: {payload['verdict']} "
        f"(tiers={tier_counts})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
