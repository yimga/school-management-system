#!/usr/bin/env python3
"""Gate: marketing-critical/enhanced CSS bundles must match source manifest."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "scripts" / "build_marketing_css_bundles.py"


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(BUILD), "--check"],
        cwd=REPO,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
