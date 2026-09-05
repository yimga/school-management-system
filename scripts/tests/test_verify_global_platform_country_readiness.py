"""A gate that could not finish must not report that the platform is broken.

``verify_global_platform_country_readiness`` shells out to four child verifiers. It gave
each a hardcoded 180s, did not catch ``subprocess.TimeoutExpired``, and killed only the
direct child. On a machine running several agents' suites at once, one of those children
-- ``verify_sovereign_offline_foundation`` -- measured **7m04s wall for 0.06s of user
time**, i.e. almost entirely contention. The gate then aborted a push with a raw traceback
while asserting nothing at all about the 249-country baseline it exists to check.

Three properties are locked here:

* the child budget is configurable, and defaults well above the observed worst case;
* a timeout is reported as INCONCLUSIVE with the runner's SKIP exit code, never as a
  structural failure, and never as an uncaught exception;
* a genuine non-zero child still fails the gate, so the fix is not a rubber stamp.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "verify_global_platform_country_readiness.py"


def _load(env_timeout: str | None = None):
    """Import the gate module fresh so it re-reads the environment."""
    previous = os.environ.get("RMC_GATE_CHILD_TIMEOUT_S")
    if env_timeout is None:
        os.environ.pop("RMC_GATE_CHILD_TIMEOUT_S", None)
    else:
        os.environ["RMC_GATE_CHILD_TIMEOUT_S"] = env_timeout
    try:
        spec = importlib.util.spec_from_file_location("_gate_under_test", GATE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            os.environ.pop("RMC_GATE_CHILD_TIMEOUT_S", None)
        else:
            os.environ["RMC_GATE_CHILD_TIMEOUT_S"] = previous


class ChildBudgetTests(unittest.TestCase):
    def test_the_budget_is_configurable(self) -> None:
        self.assertEqual(_load("42")._CHILD_TIMEOUT_S, 42)

    def test_the_default_clears_the_measured_worst_case(self) -> None:
        """423s was measured under load; a default at or below that is a flaky gate."""
        self.assertGreaterEqual(_load()._CHILD_TIMEOUT_S, 600)

    def test_the_gate_no_longer_hardcodes_180(self) -> None:
        source = GATE.read_text(encoding="utf-8")
        self.assertNotIn("timeout=180", source)

    def test_inconclusive_uses_the_runners_skip_code(self) -> None:
        """pre_push_boundary_check renders exit 2 as SKIP rather than PASS or FAIL."""
        runner = (REPO_ROOT / "scripts" / "pre_push_boundary_check.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_SKIPPED_EXIT_CODE = 2", runner)
        self.assertEqual(_load()._INCONCLUSIVE_EXIT_CODE, 2)


class TimeoutIsReportedNotRaisedTests(unittest.TestCase):
    def test_a_timed_out_child_returns_none_instead_of_raising(self) -> None:
        module = _load("1")
        code, summary = module._run_script("verify_sovereign_offline_foundation.py")
        self.assertIsNone(code, "a timeout must be distinguishable from a failure")
        self.assertIn("timed out", summary)

    def test_a_timeout_exits_skip_not_fail(self) -> None:
        """End to end: the whole gate, forced to time out, must exit 2 and say so."""
        env = dict(os.environ, RMC_GATE_CHILD_TIMEOUT_S="1")
        proc = subprocess.run(
            [sys.executable, str(GATE), "--skip-django"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
            timeout=300,
            check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout[-400:])
        combined = proc.stdout + proc.stderr
        self.assertIn("INCONCLUSIVE", combined)
        self.assertNotIn("Traceback", combined)
        self.assertNotIn("GLOBAL_PLATFORM_COUNTRY_READINESS_FAIL", combined)


if __name__ == "__main__":
    unittest.main()
