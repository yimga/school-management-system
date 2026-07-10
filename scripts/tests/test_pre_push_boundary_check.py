"""Stdlib unittest coverage for ``pre_push_boundary_check``.

Locks the two properties that make the local pre-push mirror trustworthy:
  1. Every gate the runner references resolves to a real ``scripts/*.py`` file
     (so the runner never silently "passes" a gate that has been renamed away).
  2. WARN mode never blocks a push (exit 0) while STRICT mode does (exit 1) when
     a gate fails — the whole safety contract of installing it into a shared clone.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "pre_push_boundary_check", SCRIPTS_DIR / "pre_push_boundary_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrePushBoundaryCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_module()

    def test_every_referenced_gate_script_exists(self) -> None:
        for label, argv in self.mod.GATES:
            script = SCRIPTS_DIR / argv[0]
            self.assertTrue(
                script.is_file(),
                f"gate '{label}' references missing script {script}",
            )

    def test_gate_flags_are_recognised_by_the_gate(self) -> None:
        # Each flag the runner passes must exist in the target gate's source, so
        # a flag rename in CI can't leave the runner invoking a dead switch.
        for label, argv in self.mod.GATES:
            flags = [a for a in argv[1:] if a.startswith("--")]
            if not flags:
                continue
            body = (SCRIPTS_DIR / argv[0]).read_text(encoding="utf-8", errors="ignore")
            for flag in flags:
                self.assertIn(
                    flag, body, f"gate '{label}' passes unknown flag {flag}"
                )

    def test_warn_mode_never_blocks_on_failure(self) -> None:
        self.mod.GATES = [("forced-fail", ["definitely_not_a_real_scanner_xyz.py"])]
        self.assertEqual(self.mod.main([]), 0)

    def test_strict_mode_blocks_on_failure(self) -> None:
        self.mod.GATES = [("forced-fail", ["definitely_not_a_real_scanner_xyz.py"])]
        self.assertEqual(self.mod.main(["--strict"]), 1)

    def test_strict_mode_passes_when_no_failures(self) -> None:
        self.mod.GATES = []  # nothing to run -> nothing to fail
        self.assertEqual(self.mod.main(["--strict"]), 0)

    def test_list_mode_exits_zero(self) -> None:
        self.assertEqual(self.mod.main(["--list"]), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
