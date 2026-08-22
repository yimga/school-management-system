"""Stdlib unittest coverage for ``pre_push_boundary_check``.

Locks the two properties that make the local pre-push mirror trustworthy:
  1. Every gate the runner references resolves to a real ``scripts/*.py`` file
     (so the runner never silently "passes" a gate that has been renamed away).
  2. The enforcement contract: a failed gate blocks the push BY DEFAULT (exit 1),
     and exits 0 only when someone explicitly asked for warn-only. This inverted on
     2026-08-21 — it was warn-by-default, which was safe while something downstream
     still checked, and nothing does: branch protection is unavailable on this plan
     and Actions has started no job since 2026-08-15.

Every mode case clears ``RMC_PREPUSH_STRICT`` first. Without that these tests read
the developer's own environment and pass or fail for reasons having nothing to do
with the code under test.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import unittest
from unittest import mock

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
        # Snapshot the whole environment and drop the override, so a developer who
        # happens to export RMC_PREPUSH_STRICT cannot flip these results. Restored
        # by the cleanup regardless of outcome.
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("RMC_PREPUSH_STRICT", None)
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

    def _force_one_failing_gate(self) -> None:
        """One gate that always fails, and no Django gates.

        A missing script is reported as a failure without running anything, so the
        exit-code contract is exercised deterministically and in milliseconds.
        ``DJANGO_GATES`` is emptied too: leaving it populated makes these tests boot
        Django and run the real gates, which is slow and makes the result depend on
        the tree's current cleanliness rather than on the mode being tested.
        """
        self.mod.GATES = [("forced-fail", ["definitely_not_a_real_scanner_xyz.py"])]
        self.mod.DJANGO_GATES = []

    def test_a_failing_gate_blocks_the_push_by_default(self) -> None:
        # The headline contract: no flags, no env, red gate -> push aborts.
        self._force_one_failing_gate()
        self.assertEqual(self.mod.main([]), 1)

    def test_warn_only_flag_does_not_block(self) -> None:
        self._force_one_failing_gate()
        self.assertEqual(self.mod.main(["--warn-only"]), 0)

    def test_env_override_zero_does_not_block(self) -> None:
        self._force_one_failing_gate()
        with mock.patch.dict(os.environ, {"RMC_PREPUSH_STRICT": "0"}):
            self.assertEqual(self.mod.main([]), 0)

    def test_env_override_one_still_blocks(self) -> None:
        self._force_one_failing_gate()
        with mock.patch.dict(os.environ, {"RMC_PREPUSH_STRICT": "1"}):
            self.assertEqual(self.mod.main([]), 1)

    def test_empty_env_value_is_not_an_override(self) -> None:
        # An exported-but-empty var is not a decision; it must not silently disable
        # enforcement the way a truthiness check on "" would.
        self._force_one_failing_gate()
        with mock.patch.dict(os.environ, {"RMC_PREPUSH_STRICT": ""}):
            self.assertEqual(self.mod.main([]), 1)

    def test_legacy_strict_flag_still_blocks(self) -> None:
        # --strict is now the default, but hooks and docs in the wild still pass it.
        self._force_one_failing_gate()
        self.assertEqual(self.mod.main(["--strict"]), 1)

    def test_no_failures_exits_zero(self) -> None:
        self.mod.GATES = []  # nothing to run -> nothing to fail
        self.mod.DJANGO_GATES = []
        self.assertEqual(self.mod.main([]), 0)

    def test_list_mode_exits_zero(self) -> None:
        self.assertEqual(self.mod.main(["--list"]), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
