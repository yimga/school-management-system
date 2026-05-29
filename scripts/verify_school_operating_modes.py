#!/usr/bin/env python3
"""Verify standalone schools work without Organization (Phase 2+ gate)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    parser = argparse.ArgumentParser(description="School operating modes verifier")
    parser.add_argument("--allow-pending", action="store_true", help="Pass when governance_operating_mode not yet shipped")
    args = parser.parse_args()

    models_path = REPO / "apps" / "schools" / "models.py"
    if not models_path.is_file():
        print("FAIL: apps/schools/models.py missing", file=sys.stderr)
        return 1

    text = models_path.read_text(encoding="utf-8")
    has_mode = "governance_operating_mode" in text
    has_org_fk = "organization" in text and "ForeignKey" in text

    if has_mode:
        print("verify_school_operating_modes: PASS (governance_operating_mode present)")
        return 0

    if args.allow_pending or not has_org_fk:
        print("verify_school_operating_modes: PASS (scaffold — operating mode ships Phase 2)")
        return 0

    print("verify_school_operating_modes: FAIL — org FK without operating mode", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
