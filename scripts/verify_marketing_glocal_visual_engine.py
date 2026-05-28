#!/usr/bin/env python3
"""Orchestrator: RUNMYCAMPUS-GLOCAL + VISUAL-ENGINE-10X marketing gates."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

GATES = (
    "scripts/verify_marketing_intent_viewport.py",
    "scripts/verify_lane2_external_honesty.py",
    "scripts/ensure_marketing_loops.py",
    "scripts/verify_marketing_media_manifest.py",
    "scripts/verify_marketing_loop_assets.py",
    "scripts/verify_marketing_loop_buckets_distinct.py",
    "scripts/verify_marketing_loops_hero_derived.py",
    "scripts/verify_marketing_no_video_iframes.py",
    "scripts/verify_marketing_visual_engine_sections.py",
    "scripts/verify_marketing_platform_visual_wiring.py",
    "scripts/verify_marketing_platform_pages_visual_coverage.py",
    "scripts/verify_marketing_platform_routed_dedicated.py",
    "scripts/verify_marketing_regional_routes.py",
)


def main() -> int:
    errors: list[str] = []
    for rel in GATES:
        proc = subprocess.run(
            [sys.executable, str(REPO / rel)],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            errors.append(f"{rel}:\n{proc.stderr or proc.stdout}")
    landing = REPO / "templates" / "schools" / "marketing_landing_v2.html"
    if landing.is_file():
        text = landing.read_text(encoding="utf-8")
        if "marketing_media_context" not in (REPO / "config" / "settings.py").read_text(encoding="utf-8"):
            errors.append("settings.py missing marketing_media_context processor")
        if "marketing/api/sandbox-validate" not in (REPO / "config" / "public_urls.py").read_text(encoding="utf-8"):
            errors.append("public_urls.py missing sandbox-validate route")
    else:
        errors.append("marketing_landing_v2.html missing")
    if errors:
        print("verify_marketing_glocal_visual_engine: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_marketing_glocal_visual_engine: OK (MARKETING_GLOCAL_VISUAL_ENGINE_PASS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
