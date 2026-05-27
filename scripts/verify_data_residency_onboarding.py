#!/usr/bin/env python3
"""Batch 1530 — signup and sovereignty paths assign data_region."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []

    signup = (ROOT / "apps/schools/signup_views.py").read_text(encoding="utf-8")
    if "apply_data_residency_for_new_school" not in signup:
        findings.append("signup_views missing apply_data_residency_for_new_school")

    mod = ROOT / "apps/schools/data_residency_onboarding.py"
    if not mod.is_file():
        findings.append("missing data_residency_onboarding.py")
    else:
        text = mod.read_text(encoding="utf-8")
        if "derive_default_region" not in text:
            findings.append("data_residency_onboarding missing derive_default_region")

    wizard = (ROOT / "apps/setup_studio/wizard_resolvers.py").read_text(encoding="utf-8")
    if "write_sovereignty_jurisdiction" not in wizard:
        findings.append("wizard missing write_sovereignty_jurisdiction")

    readiness = ROOT / "apps/schools/residency_readiness.py"
    if not readiness.is_file():
        findings.append("missing residency_readiness.py")

    panel = ROOT / "templates/schools/partials/data_residency_readiness_panel.html"
    if not panel.is_file():
        findings.append("missing data_residency_readiness_panel.html")

    if findings:
        print("verify_data_residency_onboarding: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_data_residency_onboarding: DATA_RESIDENCY_ONBOARDING_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
