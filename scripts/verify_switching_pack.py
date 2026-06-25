#!/usr/bin/env python3
"""Verifier: switching pack helpers and export wiring."""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    path = REPO / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    findings: list[str] = []

    pack = _text("apps/schools/offboarding_switching_pack.py")
    for sym in (
        "build_switching_pack_readme",
        "build_validation_report",
        "validation_report_json",
    ):
        if sym not in pack:
            findings.append(f"offboarding_switching_pack missing {sym}")

    service = _text("apps/schools/tenant_offboarding.py")
    if "switching/README.md" not in service:
        findings.append("run_wind_down_export must bundle switching/README.md")
    if "switching/validation_report.json" not in service:
        findings.append("run_wind_down_export must bundle validation_report.json")

    if findings:
        print("FAIL: switching pack")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("PASS: switching pack")
    return 0


if __name__ == "__main__":
    sys.exit(main())
