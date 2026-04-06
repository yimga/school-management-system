"""Phase 9: security ledger freshness + classified endpoint/SQL surface (CI subprocess gates)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_ROOT = Path(__file__).resolve().parents[3]


def _run_script(rel: str, *args: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(_ROOT / rel), *args],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"{rel} {' '.join(args)} failed (exit {proc.returncode})\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


class Phase9SecurityGatesTests(SimpleTestCase):
    def test_security_ledger_check(self) -> None:
        _run_script(
            "scripts/build_phase8_security_ledger.py",
            "--check",
            "--base",
            str(_ROOT),
        )

    def test_csrf_exempt_allowlist_lint(self) -> None:
        _run_script("scripts/lint_csrf_exempt_usage.py", "--base", str(_ROOT))

    def test_allow_any_allowlist_lint(self) -> None:
        _run_script("scripts/lint_allow_any_usage.py", "--base", str(_ROOT))

    def test_raw_sql_allowlist_lint(self) -> None:
        _run_script("scripts/lint_raw_sql_usage.py", "--base", str(_ROOT))

    def test_dashboard_density_gate(self) -> None:
        _run_script("scripts/verify_phase8_dashboard_density.py", "--base", str(_ROOT))
