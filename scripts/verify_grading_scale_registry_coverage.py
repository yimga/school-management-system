#!/usr/bin/env python3
"""Verify the global academic kernel grade scales are present AND renderable.

This gate makes two INDEPENDENT guarantees, neither of which is self-referential:

1. SEED PRESENCE (a DB precondition, not a self-write).
   The 15 canonical ``GradeScaleRegistry`` codes must be present as ``is_active``
   rows *before this gate runs* — i.e. they are the rows that ``registries``
   migration ``0008_seed_grade_scale_registry`` left in the DB the CI step migrates
   just before invoking this gate. The gate does NOT call ``ensure_grade_scale_seed()``
   itself: seeding-then-asserting-its-own-write is a tautology (``missing`` could
   never be non-empty, so migration 0008's seed was never actually exercised — delete
   0008's seed and the old gate still passed). By asserting only what the migration
   left behind, a broken or removed 0008 seed now makes this gate FAIL.

2. RENDER COVERAGE (module constants — the table report cards ACTUALLY read).
   Every registry code a school can pick during onboarding must map, through the
   operational bridge ``apps.evals.grading.REGISTRY_SCALE_TYPE_MAP``, to a
   ``scale_type`` that has a REAL renderable band table on the exact path a report
   card / gradebook / transcript renders a grade — ``apps.evals.grading.format_grade_band``
   →  ``apps.evals.models.resolve_extended_band_label`` (``EXTENDED_GRADE_BANDS``) with
   the coarse A–E fallback (``GRADING_SCALE_BANDS`` for the score axis +
   ``get_grade_letter`` over ``GRADING_SCALES`` via ``ASSESSMENT_WEIGHTS_SCALE_MAP``).
   A registry scale with no operational home, or one whose ``scale_type`` resolves no
   band table on that path, is a SILENT DISPLAY HOLE — an in-range mark renders a
   fabricated coarse fallback ("F") or nothing at all — so it makes this gate FAIL.

   The registry ``metadata['boundary_map']`` is a *different* structure: it is read
   only by this gate and the ``/api/v1/runtime`` grading-matrix JSON payload
   (``apps/api/runtime_endpoints.py``), and NO report card / gradebook / transcript /
   frontend consumes it. Certifying ``boundary_map`` therefore proved display
   correctness for a table nothing renders. It is retained below (under ``--strict``)
   ONLY as a sanity guard on that runtime-API surface — it is no longer the
   substantive coverage signal; RENDER COVERAGE above is.
"""

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


def render_coverage_gaps(
    required_codes,
    registry_scale_type_map,
    assessment_weights_scale_map,
    grading_scales_keys,
    extended_grade_bands,
    grading_scale_bands,
) -> list[str]:
    """Registry codes with NO renderable band table on the report-card render path.

    Pure over its arguments (no DB / no Django) so it is unit-testable and can be
    driven with an injected gap in a negative-control harness. Mirrors exactly what
    ``apps.evals.grading.format_grade_band(scale_type, score)`` needs to produce a
    real label rather than silently degrading to the 0–20 coarse fallback:

      * the registry code must have an operational ``scale_type``
        (``REGISTRY_SCALE_TYPE_MAP`` entry) — a school can PICK the scale, so an
        unmapped code has no engine that computes or renders it;
      * that ``scale_type`` must carry the coarse A–E axis the model reads
        (``GRADING_SCALE_BANDS`` — supplies ``score_scale`` + the legacy letter); and
      * it must resolve a DISPLAYED label either through a rich extended table
        (``EXTENDED_GRADE_BANDS`` — WAEC A1…F9, Pass/Fail, descriptors, GCSE, IB,
        CBSE, German) OR a real coarse display scale
        (``ASSESSMENT_WEIGHTS_SCALE_MAP[scale_type]`` ∈ ``GRADING_SCALES`` — the key
        ``get_grade_letter`` reads). If neither exists the render path falls back to
        ``GRADING_SCALES['0-20']`` and shows a fabricated letter for a foreign scale.
    """
    keys = set(grading_scales_keys)
    gaps: list[str] = []
    for code in required_codes:
        scale_type = registry_scale_type_map.get(code)
        if not scale_type:
            gaps.append(code)  # pickable in the catalog, no operational/render home
            continue
        if scale_type not in grading_scale_bands:
            gaps.append(code)  # no coarse score axis → model cannot render it
            continue
        renders_rich = scale_type in extended_grade_bands
        display_scale = assessment_weights_scale_map.get(scale_type)
        renders_coarse = display_scale in keys
        if not (renders_rich or renders_coarse):
            gaps.append(code)  # no rich band table AND no real coarse display scale
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    import django

    django.setup()

    from apps.registries.models import GradeScaleRegistry

    # (1) SEED PRESENCE — assert the migration's durable seed, do NOT re-seed here.
    missing = [
        code
        for code in REQUIRED_CODES
        if not GradeScaleRegistry.objects.filter(code=code, is_active=True).exists()
    ]

    # (2) RENDER COVERAGE — the table report cards actually read (evals render path).
    from apps.evals.grading import (
        ASSESSMENT_WEIGHTS_SCALE_MAP,
        GRADING_SCALES,
        REGISTRY_SCALE_TYPE_MAP,
    )
    from apps.evals.models import EXTENDED_GRADE_BANDS, GRADING_SCALE_BANDS

    render_gaps = render_coverage_gaps(
        REQUIRED_CODES,
        REGISTRY_SCALE_TYPE_MAP,
        ASSESSMENT_WEIGHTS_SCALE_MAP,
        set(GRADING_SCALES.keys()),
        EXTENDED_GRADE_BANDS,
        GRADING_SCALE_BANDS,
    )

    band_gaps: list[str] = []
    display_gaps: list[str] = []
    if args.strict:
        # Sanity guard on the runtime grading-matrix API surface only (boundary_map);
        # NOT the report-card render path — see module docstring.
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

    findings = bool(missing or render_gaps or band_gaps or display_gaps)
    payload = {
        "verdict": (
            "GRADING_SCALE_REGISTRY_FAIL"
            if findings
            else "GRADING_SCALE_REGISTRY_PASS"
        ),
        "required": list(REQUIRED_CODES),
        "missing": missing,
        "render_gaps": render_gaps,
        "band_gaps": band_gaps,
        "display_gaps": display_gaps,
        "finding_count": len(missing)
        + len(render_gaps)
        + len(band_gaps)
        + len(display_gaps),
    }
    if args.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ``missing`` and ``render_gaps`` are load-bearing on every run; band/display gaps
    # only under --strict (they need the DB rows and guard the runtime API surface).
    fatal = bool(missing or render_gaps or ((band_gaps or display_gaps) and args.strict))
    if fatal:
        print(
            "verify_grading_scale_registry_coverage: FAIL "
            f"missing={missing} render_gaps={render_gaps} "
            f"band_gaps={band_gaps} display_gaps={display_gaps}",
            file=sys.stderr,
        )
        return 1

    print(f"verify_grading_scale_registry_coverage: {payload['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
