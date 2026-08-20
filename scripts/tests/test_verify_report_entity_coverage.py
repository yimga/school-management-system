"""Stdlib unittest coverage for ``verify_report_entity_coverage``."""

from __future__ import annotations

import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_report_entity_coverage as v  # noqa: E402


class ReportEntityCoverageVerifierTests(unittest.TestCase):
    def test_live_tree_passes(self):
        self.assertEqual(v.main(), 0)


if __name__ == "__main__":
    unittest.main()
