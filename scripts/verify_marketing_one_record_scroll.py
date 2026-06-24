#!/usr/bin/env python3
"""Verify One Record Scroll marketing homepage wiring (batch 1704)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    required = (
        ROOT / "templates/marketing/partials/sections/_one_record_scroll.html",
        ROOT / "static/marketing/css/mkt-one-record-scroll.css",
        ROOT / "static/marketing/js/mkt-one-record-scroll.js",
        ROOT / "templates/marketing/homepage.html",
    )
    for path in required:
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")

    home = (ROOT / "templates/marketing/homepage.html").read_text(encoding="utf-8")
    for needle in (
        "_one_record_scroll.html",
        "mkt-one-record-scroll.css",
        "mkt-one-record-scroll.js",
    ):
        if needle not in home:
            errors.append(f"homepage.html missing {needle}")

    partial = (ROOT / "templates/marketing/partials/sections/_one_record_scroll.html").read_text(
        encoding="utf-8"
    )
    if "data-mkt-one-record-scroll" not in partial:
        errors.append("one_record_scroll partial missing data-mkt-one-record-scroll")
    for stage in (
        "_stage_speed_duel.html",
        "_stage_sovereign_wizard.html",
        "_stage_fluid_gradebook.html",
        "_stage_clinical_ledger.html",
        "_stage_rugged_console.html",
        "_stage_simulations_hub.html",
    ):
        if stage not in partial:
            errors.append(f"one_record_scroll missing stage {stage}")

    manifest = (ROOT / "scripts/marketing_css_bundle_manifest.json").read_text(encoding="utf-8")
    if "mkt-one-record-scroll.css" not in manifest:
        errors.append("marketing_css_bundle_manifest.json missing mkt-one-record-scroll.css")

    if errors:
        for err in errors:
            print(f"MARKETING_ONE_RECORD_SCROLL_FAIL: {err}")
        return 1

    print("MARKETING_ONE_RECORD_SCROLL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
