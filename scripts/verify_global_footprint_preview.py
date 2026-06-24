#!/usr/bin/env python3
"""Verify Global Footprint browseable preview artifact matches template contract (batch 1717)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/generate_global_footprint_preview.py"
PREVIEW = ROOT / "artifacts/global-footprint-section-preview.html"
TEMPLATE = ROOT / "templates/partials/cockpit/_live_world_map.html"

ARTIFACT_MARKERS = (
    "rmc-globe-master-lab",
    "rmc-world-globe-data",
    "data-rmc-offline-surface",
    "rmc-world-globe-loader.js",
    "rmc-world-globe-bridge.js",
)

UNHASHED_JS = (
    "rmc-world-globe-loader.js",
    "rmc-world-globe-bridge.js",
    "rmc-world-globe-wow-plus.js",
    "rmc-world-globe-surface-elevation.js",
)

HASHED_GLOBE_JS = re.compile(r"/static/js/rmc-world-globe-[a-z0-9-]+\.[a-f0-9]{8,}\.js")


def main() -> int:
    errors: list[str] = []

    if not GENERATOR.is_file():
        errors.append("missing scripts/generate_global_footprint_preview.py")
    else:
        gen = GENERATOR.read_text(encoding="utf-8")
        for needle in ("render_to_string", "_live_world_map.html", "re.sub"):
            if needle not in gen:
                errors.append(f"generator missing {needle!r}")

    if not TEMPLATE.is_file():
        errors.append("missing templates/partials/cockpit/_live_world_map.html")

    if not PREVIEW.is_file():
        errors.append(
            "missing artifacts/global-footprint-section-preview.html — "
            "run python scripts/generate_global_footprint_preview.py"
        )
    else:
        body = PREVIEW.read_text(encoding="utf-8")
        for marker in ARTIFACT_MARKERS:
            if marker not in body:
                errors.append(f"preview artifact missing {marker!r}")
        for js in UNHASHED_JS:
            if f"/static/js/{js}" not in body:
                errors.append(f"preview artifact missing unhashed {js}")
        if HASHED_GLOBE_JS.search(body):
            errors.append("preview artifact still contains hashed globe bundle paths")

    if errors:
        for err in errors:
            print(f"GLOBAL_FOOTPRINT_PREVIEW_FAIL: {err}")
        return 1

    print("GLOBAL_FOOTPRINT_PREVIEW_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
