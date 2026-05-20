#!/usr/bin/env python3
"""Shim: interaction integrity contract → verify_interaction_integrity_completion.py"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "scripts" / "verify_interaction_integrity_completion.py"


def main() -> int:
    if not TARGET.is_file():
        print(f"Missing {TARGET}")
        return 1
    proc = subprocess.run([sys.executable, str(TARGET)], cwd=ROOT)
    if proc.returncode == 0:
        print("INTERACTION_INTEGRITY_CONTRACT_PASS (delegated)")
    else:
        print("INTERACTION_INTEGRITY_CONTRACT_FAIL (delegated)")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
