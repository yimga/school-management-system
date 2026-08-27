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

import contextlib
import importlib.util
import io
import os
import pathlib
import sys
import types
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


class UnrunGateReportingTests(unittest.TestCase):
    """A gate that did not run must not be reported as a gate that passed.

    Proven on 2026-08-27: with Django unimportable, all 8 DJANGO_GATES printed
    SKIP and the run still printed "All boundary gates green - safe to push."
    and exited 0. The skipped set was the security-relevant half -- the three
    RLS tenant-isolation gates, unscoped-shared-tenant-admin, both URL-contract
    gates -- and the hook reads exit 0 as permission.

    The EXIT CODE is deliberately unchanged. Skipping when the toolchain is
    absent is an intentional trade-off (see _SKIPPED_EXIT_CODE: failing would
    block every developer who does not have it). Only the sentence was wrong.
    """

    def setUp(self) -> None:
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("RMC_PREPUSH_STRICT", None)
        self.mod = _load_module()

    def _run_capturing(self, argv=None) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self.mod.main(argv or [])
        return code, buf.getvalue()

    def _all_django_gates_unrunnable(self) -> None:
        self.mod.GATES = []
        self.mod.DJANGO_GATES = [("fake-django-gate", ["nonexistent_gate.py"])]
        patcher = mock.patch.object(
            self.mod, "_django_python", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unrun_gates_are_not_reported_as_all_green(self) -> None:
        self._all_django_gates_unrunnable()
        _, out = self._run_capturing()
        self.assertNotIn(
            "All boundary gates green",
            out,
            "a run with un-run gates still claimed every gate was green",
        )

    def test_unrun_gates_are_named_as_unchecked(self) -> None:
        self._all_django_gates_unrunnable()
        _, out = self._run_capturing()
        self.assertIn("did NOT run", out)
        self.assertIn("UNCHECKED", out)

    def test_skipping_still_exits_zero(self) -> None:
        # The deliberate trade-off, pinned so a later edit cannot quietly turn
        # a missing toolchain into a blocked push.
        self._all_django_gates_unrunnable()
        code, _ = self._run_capturing()
        self.assertEqual(code, 0)

    def test_a_run_with_nothing_skipped_still_says_all_green(self) -> None:
        # The message must not cry wolf on a genuinely complete run.
        self.mod.GATES = []
        self.mod.DJANGO_GATES = []
        code, out = self._run_capturing()
        self.assertEqual(code, 0)
        self.assertIn("All boundary gates green", out)


class InterpreterResolutionTests(unittest.TestCase):
    """The Django gates must find an interpreter that actually has Django.

    The pre-push hook invokes bare ``python``. On the ordinary setup that is the
    SYSTEM interpreter, which carries none of the project dependencies -- so
    every Django gate skipped. Falling through to the project venv is what makes
    those gates run at all for a normal contributor.
    """

    def setUp(self) -> None:
        self.mod = _load_module()

    def test_candidates_begin_with_the_running_interpreter(self) -> None:
        self.assertEqual(self.mod._interpreter_candidates()[0], sys.executable)

    def test_candidates_include_a_project_venv_when_one_exists(self) -> None:
        candidates = self.mod._interpreter_candidates()
        venvs = [c for c in candidates if ".venv" in c]
        if not venvs:
            self.skipTest("no .venv in this checkout or its main worktree")
        self.assertTrue(venvs)

    def test_a_linked_worktree_reaches_the_main_checkout(self) -> None:
        # A linked worktree has no .venv of its own; the git common dir points
        # back to the checkout that does. Without this the fallback finds nothing
        # in exactly the trees where the work happens.
        source = (SCRIPTS_DIR / 'pre_push_boundary_check.py').read_text(
            encoding="utf-8", errors="ignore"
        )
        self.assertIn("--git-common-dir", source)

    def test_django_python_falls_through_to_the_next_candidate(self) -> None:
        tried: list[str] = []

        def fake_run(cmd, **kwargs):
            tried.append(cmd[0])
            code = 0 if cmd[0] == "/venv/python" else 1
            return types.SimpleNamespace(returncode=code, stdout="", stderr="")

        self.mod._DJANGO_PYTHON_CACHE.clear()
        with mock.patch.object(
            self.mod, "_interpreter_candidates",
            return_value=["/system/python", "/venv/python"],
        ), mock.patch.object(self.mod.subprocess, "run", side_effect=fake_run):
            self.assertEqual(self.mod._django_python(), "/venv/python")
        self.assertEqual(tried, ["/system/python", "/venv/python"])

    def test_an_unlaunchable_interpreter_is_skipped_not_fatal(self) -> None:
        def fake_run(cmd, **kwargs):
            if cmd[0] == "/missing/python":
                raise OSError("no such file")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        self.mod._DJANGO_PYTHON_CACHE.clear()
        with mock.patch.object(
            self.mod, "_interpreter_candidates",
            return_value=["/missing/python", "/venv/python"],
        ), mock.patch.object(self.mod.subprocess, "run", side_effect=fake_run):
            self.assertEqual(self.mod._django_python(), "/venv/python")

    def test_no_candidate_with_django_returns_none(self) -> None:
        def fake_run(cmd, **kwargs):
            return types.SimpleNamespace(returncode=1, stdout="", stderr="")

        self.mod._DJANGO_PYTHON_CACHE.clear()
        with mock.patch.object(
            self.mod, "_interpreter_candidates",
            return_value=["/a/python", "/b/python"],
        ), mock.patch.object(self.mod.subprocess, "run", side_effect=fake_run):
            self.assertIsNone(self.mod._django_python())
            self.assertFalse(self.mod._django_available())

    def test_run_gate_uses_the_interpreter_it_is_given(self) -> None:
        seen: list[str] = []

        def fake_run(cmd, **kwargs):
            seen.append(cmd[0])
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(self.mod.subprocess, "run", side_effect=fake_run):
            self.mod._run_gate(
                "probe",
                ["pre_push_boundary_check.py"],
                python="/chosen/python",
            )
        self.assertEqual(seen, ["/chosen/python"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
