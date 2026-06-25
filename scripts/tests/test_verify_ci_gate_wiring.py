"""Stdlib unittest coverage for ``verify_ci_gate_wiring``.

Locks the meta-gate that asserts every critical CI gate stays wired into a
workflow. The ``test_all_required_gates_are_wired`` case doubles as the live
calibration — it fails the moment a REQUIRED_GATES entry stops being invoked
in any ``.github/workflows/*.yml`` (the exact regression this gate prevents).
"""

from __future__ import annotations

import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_ci_gate_wiring as v  # noqa: E402


class WiringTests(unittest.TestCase):
    def test_all_required_gates_are_wired(self):
        # Live calibration: every REQUIRED_GATES entry must be invoked in some
        # workflow file in the real tree. Empty == fully enforced.
        unwired = v.find_unwired()
        self.assertEqual(unwired, [], f"un-wired gates: {unwired}")

    def test_detects_a_missing_gate(self):
        # A bogus required gate that appears in no workflow is reported.
        fake = (
            ("scripts/scan_import_reference_integrity.py", "architectural-boundaries.yml"),
            ("scripts/__definitely_not_a_real_gate__.py", "ci.yml"),
        )
        out = v.find_unwired(fake)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["script"], "scripts/__definitely_not_a_real_gate__.py")

    def test_real_gate_passes_in_isolation(self):
        one = (("scripts/verify_template_reference_integrity.py", "ci.yml"),)
        self.assertEqual(v.find_unwired(one), [])

    def test_payload_shape(self):
        p = v._payload([{"script": "x", "expected_workflow": "y"}])
        self.assertEqual(p["finding_count"], 1)
        self.assertEqual(p["required_count"], len(v.REQUIRED_GATES))
        self.assertIn("rule", p)

    def test_registry_is_nonempty_and_paths_shaped(self):
        self.assertGreaterEqual(len(v.REQUIRED_GATES), 4)
        for script, workflow in v.REQUIRED_GATES:
            self.assertTrue(script.startswith("scripts/") and script.endswith(".py"), script)
            self.assertTrue(workflow.endswith(".yml"), workflow)


if __name__ == "__main__":
    unittest.main()
