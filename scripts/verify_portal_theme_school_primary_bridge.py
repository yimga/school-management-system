#!/usr/bin/env python3
"""Backward-compatible alias — delegates to verify_portal_theme_token_spine.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    script = ROOT / "scripts" / "verify_portal_theme_token_spine.py"
    proc = subprocess.run([sys.executable, str(script)], cwd=ROOT)
    if proc.returncode == 0:
        print("verify_portal_theme_school_primary_bridge: PASS")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
