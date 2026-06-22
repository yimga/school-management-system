"""Every <th> must declare a header association (a11y wave, 2026-06-22).

Runs scripts/scan_th_scope.py inside the test suite so the zero-tolerance gate
is enforced on every CI run (not only via the architectural-boundaries workflow).
A `<th>` with neither scope= nor headers= is ambiguous to screen readers in any
non-trivial table (WCAG 1.3.1).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]
SCANNER = REPO / "scripts" / "scan_th_scope.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("scan_th_scope", SCANNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ThScopeTests(SimpleTestCase):
    def test_no_th_without_scope(self) -> None:
        mod = _load_scanner()
        findings = mod.collect()
        self.assertEqual(
            findings, [],
            "<th> without scope=/headers= (add scope=\"col\"/\"row\", or a "
            "<!-- th-scope-allow: reason --> marker):\n  " + "\n  ".join(findings),
        )

    def test_row_header_tables_use_scope_row(self) -> None:
        # the vertical key-value table fixed in this wave heads its rows, not cols
        src = (REPO / "templates/evals/resolve_offline_conflict.html").read_text(encoding="utf-8")
        self.assertIn('<th scope="row">Seq 1:</th>', src)
        self.assertNotIn('<th scope="col">Seq 1:</th>', src)
        self.assertNotIn("<th>Exam:</th>", src)
