"""scan_rls_table_coverage enumerates nested _TABLES tuples and scalar TABLE=."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

from scan_rls_table_coverage import _string_literals  # noqa: E402


class EnumerateRlsTableLiteralsTests(unittest.TestCase):
    def test_nested_tuple_and_scalar_table_are_collected(self):
        src = '''
TABLE = "reports_reportcardbatch"
_TABLES = (
    ("schools_immunizationrecord", "immunizationrecord"),
    ("schools_vaccinerequirement", "vaccinerequirement"),
)
TABLES = ["sync_engine_edgesyncrun"]
'''
        tree = ast.parse(src)
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                found.update(_string_literals(node.value))
        self.assertIn("reports_reportcardbatch", found)
        self.assertIn("schools_immunizationrecord", found)
        self.assertIn("schools_vaccinerequirement", found)
        self.assertIn("sync_engine_edgesyncrun", found)
        self.assertIn("immunizationrecord", found)


if __name__ == "__main__":
    unittest.main()
