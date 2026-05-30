"""v4.00.92 — Full-sweep validation runner across Waves 1-26.

Discovers every ``scripts/smoke_v4_00_*.py`` file in lexicographic order,
runs it as a subprocess, tallies the green / fail counts per wave, and
prints a compact summary. Intended for the final wave-26 validation pass.

Exit code:
  * 0 if every smoke completes with zero FAIL lines
  * 1 if any smoke prints at least one FAIL line OR returns non-zero
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_SMOKE_PATTERN = re.compile(r"^smoke_v4_00_.*\.py$")
_OK_LINE = re.compile(r"^(?:\s*OK\s+|\s*\[OK\b)")
_FAIL_LINE = re.compile(r"^\s*FAIL\b|^\s*\[FAIL\b")


def _discover_smokes() -> list[Path]:
    candidates = sorted(
        p for p in (_REPO_ROOT / "scripts").iterdir()
        if p.is_file() and _SMOKE_PATTERN.match(p.name)
    )
    return candidates


def _run_one(smoke: Path) -> tuple[int, int, int]:
    """Return (oks, fails, exit_code)."""
    result = subprocess.run(
        [sys.executable, str(smoke)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = result.stdout + result.stderr
    oks = sum(1 for line in out.splitlines() if _OK_LINE.match(line))
    fails = sum(1 for line in out.splitlines() if _FAIL_LINE.match(line))
    return oks, fails, result.returncode


def main() -> int:
    smokes = _discover_smokes()
    if not smokes:
        print("No smoke scripts found", file=sys.stderr)
        return 1

    grand_ok = 0
    grand_fail = 0
    failing = []
    print("=" * 70)
    print(f"v4.00.92 — Full-sweep validation across {len(smokes)} smokes")
    print("=" * 70)
    for smoke in smokes:
        try:
            oks, fails, rc = _run_one(smoke)
        except subprocess.TimeoutExpired:
            print(f"  {smoke.name:50s} TIMEOUT")
            grand_fail += 1
            failing.append(smoke.name)
            continue
        marker = "OK" if (fails == 0 and rc == 0) else "FAIL"
        print(f"  {smoke.name:50s} {marker:5s} OK={oks:3d} FAIL={fails:2d}")
        grand_ok += oks
        grand_fail += fails
        if fails > 0 or rc != 0:
            failing.append(smoke.name)

    print("=" * 70)
    print(f"Total cases: {grand_ok} OK / {grand_fail} FAIL across {len(smokes)} waves")
    if failing:
        print(f"Failing smokes ({len(failing)}):")
        for name in failing:
            print(f"  - {name}")
        return 1
    print("ALL GREEN — 0 regressions across the full 22+ wave sweep.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
