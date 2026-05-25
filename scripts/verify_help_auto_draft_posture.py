#!/usr/bin/env python3
"""Verify HELP_ZERO_RESULT_AUTO_DRAFT_KB defaults for staging/production/cloud."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    settings_path = ROOT / "config" / "settings.py"
    text = settings_path.read_text(encoding="utf-8", errors="replace")
    checks = [
        "_IS_PRODUCTION_OR_STAGING" in text,
        "_HELP_AUTO_DRAFT_DEFAULT" in text,
        'HELP_ZERO_RESULT_AUTO_DRAFT_KB = os.getenv(\n    "HELP_ZERO_RESULT_AUTO_DRAFT_KB", _HELP_AUTO_DRAFT_DEFAULT\n)' in text
        or 'HELP_ZERO_RESULT_AUTO_DRAFT_KB = os.getenv(\r\n    "HELP_ZERO_RESULT_AUTO_DRAFT_KB", _HELP_AUTO_DRAFT_DEFAULT\r\n)' in text,
        "maybe_auto_draft_from_content_gap" in (ROOT / "apps/portal/help_content_gaps.py").read_text(
            encoding="utf-8", errors="replace"
        ),
    ]
    if not all(checks):
        print("verify_help_auto_draft_posture: FAIL", file=sys.stderr)
        return 1

    tree = ast.parse(text)
    prod_default_on = '_HELP_AUTO_DRAFT_DEFAULT = "1" if _IS_PRODUCTION_OR_STAGING' in text
    if not prod_default_on:
        print("verify_help_auto_draft_posture: staging/prod default not ON", file=sys.stderr)
        return 1

    print("verify_help_auto_draft_posture: HELP_AUTO_DRAFT_POSTURE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
