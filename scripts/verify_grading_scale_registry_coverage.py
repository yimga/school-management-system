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


def _boundary_display_ok(boundary) -> bool:
    """A band table is DISPLAYABLE (not merely present) when every band carries a
    non-empty ``grade`` label AND a representative mid-range score resolves to one
    of those labels. That catches an unlabeled band or a coverage hole where an
    in-range mark would render blank. Range-only scales display the numeric value
    itself and are checked separately (they need no band label)."""
    entries = [b for b in boundary if isinstance(b, dict)]
    if len(entries) < 2:
        return False
    if not all(isinstance(b.get("grade"), str) and b.get("grade").strip() for b in entries):
        return False
    try:
        lo = min(float(b["min"]) for b in entries)
        hi = max(float(b["max"]) for b in entries)
    except (KeyError, TypeError, ValueError):
        return False
    mid = (lo + hi) / 2.0
    for b in entries:
        try:
            if float(b["min"]) <= mid <= float(b["max"]):
                return bool(b.get("grade") and b["grade"].strip())
        except (KeyError, TypeError, ValueError):
            continue
    return False  # mid-range score fell in no band → a display coverage hole


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
    display_gaps: list[str] = []
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
            # A band-based scale must not just HAVE a band table — it must render a
            # display label for an in-range score (labeled bands, no coverage hole).
            # Range-only scales display the numeric value and need no band label.
            if has_bands and not _boundary_display_ok(boundary):
                display_gaps.append(code)
    payload = {
        "verdict": (
            "GRADING_SCALE_REGISTRY_PASS"
            if not missing and not band_gaps and not display_gaps
            else "GRADING_SCALE_REGISTRY_FAIL"
        ),
        "required": list(REQUIRED_CODES),
        "missing": missing,
        "band_gaps": band_gaps,
        "display_gaps": display_gaps,
        "finding_count": len(missing) + len(band_gaps) + len(display_gaps),
    }
    if args.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if (missing or band_gaps or display_gaps) and args.strict:
        print(
            "verify_grading_scale_registry_coverage: FAIL "
            f"missing={missing} band_gaps={band_gaps} display_gaps={display_gaps}",
            file=sys.stderr,
        )
        return 1

    print(f"verify_grading_scale_registry_coverage: {payload['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
