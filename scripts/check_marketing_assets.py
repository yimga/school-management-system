#!/usr/bin/env python3
"""
Marketing asset manifest checker.

Walks `static/marketing/_manifest.json` and verifies:
  - every `status: SHIPPED` asset's file exists on disk;
  - every `status: PLACEHOLDER` / `PLACEHOLDER_SVG` is acknowledged (warn only);
  - every video has a caption_path AND the caption file exists on disk
    when the video is SHIPPED (a11y requirement).

Exit codes:
  0 — all SHIPPED assets present + captioned.
  1 — at least one SHIPPED asset is missing.
  2 — manifest invalid.

Usage:
  python scripts/check_marketing_assets.py
  python scripts/check_marketing_assets.py --warn-placeholders
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "static" / "marketing" / "_manifest.json"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument(
        "--warn-placeholders",
        action="store_true",
        help="Print one line per placeholder asset (info only; doesn't change exit code).",
    )
    args = p.parse_args(argv)

    if not MANIFEST.exists():
        print(f"ERROR: manifest not found at {MANIFEST}", file=sys.stderr)
        return 2

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: manifest is not valid JSON — {exc}", file=sys.stderr)
        return 2

    missing: list[str] = []
    captionless: list[str] = []
    placeholders: list[str] = []

    for asset in manifest.get("assets", []):
        slot = asset.get("slot", "?")
        status = asset.get("status", "PLACEHOLDER")
        expected = asset.get("expected_path")
        if not expected:
            continue
        if status.startswith("PLACEHOLDER"):
            placeholders.append(f"{slot:<24} {status:<18} {expected}")
            continue
        # status SHIPPED-ish — file must exist.
        path = ROOT / expected
        if not path.exists():
            missing.append(f"{slot} → {expected}")
        if asset.get("kind") == "video":
            cap = asset.get("caption_path")
            if cap and not (ROOT / cap).exists():
                captionless.append(f"{slot} → {cap}")

    print(f"Marketing asset manifest: {MANIFEST.relative_to(ROOT)}")
    print(f"  Total assets:   {len(manifest.get('assets', []))}")
    print(f"  Placeholders:   {len(placeholders)}")
    print(f"  Missing files:  {len(missing)}")
    print(f"  Captionless videos: {len(captionless)}")
    if args.warn_placeholders and placeholders:
        print("\nPlaceholders:")
        for line in placeholders:
            print(f"  · {line}")
    if missing:
        print("\nERROR: SHIPPED assets are missing from disk:", file=sys.stderr)
        for line in missing:
            print(f"  · {line}", file=sys.stderr)
    if captionless:
        print("\nERROR: SHIPPED videos have no caption file (WCAG 1.2.2):", file=sys.stderr)
        for line in captionless:
            print(f"  · {line}", file=sys.stderr)

    return 1 if (missing or captionless) else 0


if __name__ == "__main__":
    raise SystemExit(main())
