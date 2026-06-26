#!/usr/bin/env python3
"""Verify global academic kernel grade-scale seeds are present in the registry."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_PATH = REPO / "docs" / "generated" / "grading_scale_registry_coverage.json"

REQUIRED_CODES = (
    "0-20",
    "0-100",
    "GPA_4",
    "LETTER",
    "PASS_FAIL",
    "NUMERIC_1_5",
    "WAEC_LETTER",
    "STANDARD_SCORE_T",
    "QUALITATIVE_PD",
    "UK_GCSE_9_1",
    "IB_1_7",
    "GERMAN_1_6",
    "CBSE_10",
    "FRENCH_0_20",
    "US_LETTER",
)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    import django

    django.setup()

    from apps.registries.models import GradeScaleRegistry
    from apps.registries.services import ensure_grade_scale_seed

    ensure_grade_scale_seed()
    missing = [
        code
        for code in REQUIRED_CODES
        if not GradeScaleRegistry.objects.filter(code=code, is_active=True).exists()
    ]
    band_gaps: list[str] = []
    if args.strict:
        for code in REQUIRED_CODES:
            row = GradeScaleRegistry.objects.filter(code=code, is_active=True).first()
            if row is None:
                continue
            rng = row.range_definition if isinstance(row.range_definition, dict) else {}
            meta = row.metadata if isinstance(row.metadata, dict) else {}
            boundary = meta.get("boundary_map")
            has_range = "min" in rng and "max" in rng
            has_bands = isinstance(boundary, list) and len(boundary) >= 2
            if not has_range and not has_bands:
                band_gaps.append(code)
    payload = {
        "verdict": (
            "GRADING_SCALE_REGISTRY_PASS"
            if not missing and not band_gaps
            else "GRADING_SCALE_REGISTRY_FAIL"
        ),
        "required": list(REQUIRED_CODES),
        "missing": missing,
        "band_gaps": band_gaps,
        "finding_count": len(missing) + len(band_gaps),
    }
    if args.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if (missing or band_gaps) and args.strict:
        print(
            f"verify_grading_scale_registry_coverage: FAIL missing={missing} band_gaps={band_gaps}",
            file=sys.stderr,
        )
        return 1

    print(f"verify_grading_scale_registry_coverage: {payload['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
