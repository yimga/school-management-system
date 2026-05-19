#!/usr/bin/env python3
"""Run all marketing frontend + impact gates; exit 0 only when prompt is 100% complete."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

GATES = (
    ("build_marketing_css_bundles.py", [sys.executable, "scripts/build_marketing_css_bundles.py"]),
    ("generate_marketing_frontend_defect_log.py --write", [sys.executable, "scripts/generate_marketing_frontend_defect_log.py", "--write"]),
    ("verify_marketing_seo_shell.py", [sys.executable, "scripts/verify_marketing_seo_shell.py"]),
    ("verify_marketing_impact_layer.py", [sys.executable, "scripts/verify_marketing_impact_layer.py"]),
    ("verify_marketing_css_bundles_fresh.py", [sys.executable, "scripts/verify_marketing_css_bundles_fresh.py"]),
    ("verify_marketing_public_shell.py", [sys.executable, "scripts/verify_marketing_public_shell.py"]),
    ("verify_marketing_hero_media.py", [sys.executable, "scripts/verify_marketing_hero_media.py"]),
    ("verify_marketing_frontend_completion.py", [sys.executable, "scripts/verify_marketing_frontend_completion.py"]),
    ("verify_marketing_redesign_prompt_contract.py", [sys.executable, "scripts/verify_marketing_redesign_prompt_contract.py"]),
    ("verify_marketing_sweep2.py", [sys.executable, "scripts/verify_marketing_sweep2.py"]),
    ("verify_marketing_gear2_completion.py", [sys.executable, "scripts/verify_marketing_gear2_completion.py"]),
    ("verify_marketing_homepage_render.py", [sys.executable, "scripts/verify_marketing_homepage_render.py"]),
    ("verify_marketing_production_smoke.py", [sys.executable, "scripts/verify_marketing_production_smoke.py"]),
)


def main() -> int:
    failed: list[str] = []
    for label, cmd in GATES:
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        if proc.returncode != 0:
            failed.append(label)
            print(f"FAIL: {label}", file=sys.stderr)
            print(proc.stderr or proc.stdout, file=sys.stderr)
        else:
            line = (proc.stdout or "").strip().splitlines()
            print(f"OK: {label}" + (f" — {line[-1]}" if line else ""))

    if failed:
        print(f"\naudit_marketing_frontend_100: FAIL ({len(failed)} gate(s))", file=sys.stderr)
        return 1

    print("\naudit_marketing_frontend_100: PASS — marketing frontend prompt 100% complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
