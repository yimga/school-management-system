#!/usr/bin/env python3
"""Assert public marketing interactives carry visible simulated-data disclosure (batch 1616)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SPEED_DUEL = ROOT / "templates/marketing/partials/sections/_hero_speed_duel.html"
ZERO_UI = ROOT / "templates/marketing/partials/sections/_zero_ui_lab.html"

SPEED_DISCLOSURE = "Simulated benchmarks"
ZERO_UI_DISCLOSURE = "Client-side mock"


def main() -> int:
    errors: list[str] = []

    for path in (SPEED_DUEL, ZERO_UI):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT).as_posix()}")

    if errors:
        print("verify_marketing_simulated_benchmark_disclosure: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    speed_text = SPEED_DUEL.read_text(encoding="utf-8")
    if SPEED_DISCLOSURE not in speed_text:
        errors.append(
            f"{SPEED_DUEL.relative_to(ROOT).as_posix()} must expose visible simulated benchmark disclosure"
        )
    if "mkt-edt-illustrative-pill" not in speed_text:
        errors.append("speed duel section must use mkt-edt-illustrative-pill disclosure grammar")

    zero_text = ZERO_UI.read_text(encoding="utf-8")
    if ZERO_UI_DISCLOSURE not in zero_text:
        errors.append(
            f"{ZERO_UI.relative_to(ROOT).as_posix()} must expose visible client-side mock disclosure"
        )
    if "simulated" not in zero_text.lower():
        errors.append("zero-ui lab must mark simulated surfaces in aria-label or disclosure copy")

    if errors:
        print("verify_marketing_simulated_benchmark_disclosure: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_marketing_simulated_benchmark_disclosure: "
        "MARKETING_SIMULATED_BENCHMARK_DISCLOSURE_PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
