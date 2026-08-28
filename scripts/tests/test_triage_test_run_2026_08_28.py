"""The triage tool must not become a place to hide failures.

Its whole value is answering "did anything NEW break?" against a suite that is
red for reasons already written down. That value evaporates the moment it can
be used to mark a real bug as acceptable, or the moment a red that got fixed
stays on the list unchallenged. These tests pin both edges.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import triage_test_run as triage  # noqa: E402


UNITTEST_LOG = """
FAIL: test_alpha (apps.finance.tests.test_x.Case.test_alpha)
ERROR: test_beta (apps.academics.tests.test_y.Case.test_beta)
Ran 120 tests in 42.0s
FAILED (failures=1, errors=1)
"""

PYTEST_LOG = """
FAILED apps/migration_cloud/tests/test_z.py::Case::test_gamma - AssertionError
ERROR apps/migration_cloud/tests/test_z.py::Case::test_delta
Ran 12 tests in 3.0s
"""


class ParserTests(unittest.TestCase):
    def test_reads_the_unittest_form(self):
        ids = [f["test"] for f in triage.parse_failures(UNITTEST_LOG)]
        self.assertIn("apps.finance.tests.test_x.Case.test_alpha", ids)
        self.assertIn("apps.academics.tests.test_y.Case.test_beta", ids)

    def test_reads_the_pytest_form(self):
        ids = [f["test"] for f in triage.parse_failures(PYTEST_LOG)]
        self.assertIn("apps/migration_cloud/tests/test_z.py::Case::test_gamma", ids)
        self.assertIn("apps/migration_cloud/tests/test_z.py::Case::test_delta", ids)

    def test_a_green_run_has_no_failures(self):
        self.assertEqual(triage.parse_failures("Ran 10 tests in 1s\n\nOK\n"), [])

    def test_errors_are_failures_too(self):
        # An ERROR is a test that did not even get to assert. Treating only FAIL
        # as a failure is how a collection error reads as a pass.
        kinds = {f["kind"] for f in triage.parse_failures(UNITTEST_LOG)}
        self.assertIn("ERROR", kinds)


class RegistryDisciplineTests(unittest.TestCase):
    def test_an_entry_without_a_reason_is_a_problem(self):
        problems = triage.registry_problems({"tests": {"a.b.C.d": {"class": "env"}}})
        self.assertTrue(any("no reason" in p for p in problems))

    def test_an_unknown_class_is_a_problem(self):
        problems = triage.registry_problems(
            {"tests": {"a.b.C.d": {"reason": "x", "class": "whatever"}}}
        )
        self.assertTrue(any("class must be one of" in p for p in problems))

    def test_a_well_formed_entry_is_accepted(self):
        self.assertEqual(
            triage.registry_problems(
                {"tests": {"a.b.C.d": {"reason": "needs Ollama", "class": "env"}}}
            ),
            [],
        )

    def test_the_committed_registry_is_well_formed(self):
        # The real one. It goes red the moment somebody adds a blank cheque.
        self.assertEqual(triage.registry_problems(triage.load_registry()), [])


if __name__ == "__main__":
    unittest.main()
