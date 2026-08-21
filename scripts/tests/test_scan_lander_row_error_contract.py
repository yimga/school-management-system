"""Unit tests for the lander row-error contract gate.

Stdlib only, like its sibling scanner tests — the gate runs in the deps-free
boundary job, so its tests must too.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "scripts" / "scan_lander_row_error_contract.py"


def _load():
    spec = importlib.util.spec_from_file_location("_lander_contract_gate", SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load()
FAKE = Path("apps/migration_cloud/landers/probe_lander.py")


def scan(src: str):
    return gate.scan_source(FAKE, src)


def kinds(src: str):
    return sorted(f["kind"] for f in scan(src))


class ItCatchesTheRowBeingThrownAwayTests(unittest.TestCase):
    """The finding the whole gate exists for."""

    def test_bare_error_append_is_a_finding(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                "    for row in rows:\n"
                '        result.errors.append("boom")\n'
            ),
            ["bare_error_append"],
        )

    def test_it_does_not_matter_what_the_result_variable_is_called(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, out):\n"
                "    for row in rows:\n"
                '        out.errors.append("boom")\n'
            ),
            ["bare_error_append"],
        )

    def test_a_held_row_with_no_record_at_all_is_a_finding(self):
        """`quarantined += 1` alone counts a row the review table never shows."""
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                "    for row in rows:\n"
                "        result.quarantined += 1\n"
            ),
            ["bare_quarantine_increment"],
        )

    def test_the_pair_reports_both_halves(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                "    for row in rows:\n"
                "        result.quarantined += 1\n"
                '        result.errors.append("boom")\n'
            ),
            ["bare_error_append", "bare_quarantine_increment"],
        )


class ItCatchesAReasonNobodyDeclaredTests(unittest.TestCase):
    def test_record_row_error_without_reason_code_is_a_finding(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                "    for row in rows:\n"
                '        record_row_error(result, row, "boom")\n'
            ),
            ["undeclared_reason_code"],
        )

    def test_declaring_the_reason_is_clean(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                "    for row in rows:\n"
                '        record_row_error(result, row, "boom", reason_code=LANDER_ERROR)\n'
            ),
            [],
        )

    def test_a_field_hint_alone_is_not_enough(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                '    record_row_error(result, row, "boom", field="dob")\n'
            ),
            ["undeclared_reason_code"],
        )


class ItStaysSilentWhereItShouldTests(unittest.TestCase):
    def test_the_contracts_own_implementation_is_exempt(self):
        """record_row_error IS the one place allowed to touch the raw fields."""
        self.assertEqual(
            kinds(
                "def record_row_error(result, row, message, *, reason_code=None):\n"
                "    result.quarantined += 1\n"
                "    result.errors.append(message)\n"
            ),
            [],
        )

    def test_record_row_note_is_not_a_held_row(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                '    record_row_note(result, "sweep failed")\n'
            ),
            [],
        )

    def test_an_unparseable_file_is_another_gates_finding(self):
        """Reporting it twice buries the report that says how to fix it."""
        self.assertEqual(scan("def land(:\n"), [])

    def test_appending_to_something_that_is_not_errors_is_ignored(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                "    result.created_ids.append(7)\n"
                '    result.notes.append({"note": "x"})\n'
            ),
            [],
        )


class TheAllowMarkerTests(unittest.TestCase):
    def test_marker_on_the_line_above_waives_it(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                "    # lander-contract-allow: probe\n"
                '    result.errors.append("boom")\n'
            ),
            [],
        )

    def test_marker_on_the_same_line_waives_it(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                '    result.errors.append("boom")  # lander-contract-allow: probe\n'
            ),
            [],
        )

    def test_an_unrelated_comment_does_not(self):
        self.assertEqual(
            kinds(
                "def land(self, rows, result):\n"
                "    # TODO fix this later\n"
                '    result.errors.append("boom")\n'
            ),
            ["bare_error_append"],
        )


class TheLiveTreeTests(unittest.TestCase):
    """Calibration: the real landers must be clean, and the gate must be able to
    see them (a scanner that finds nothing because it is looking nowhere passes
    the same way a clean tree does)."""

    def test_the_real_landers_scan_clean(self):
        findings = gate.scan()
        self.assertEqual(
            findings,
            [],
            msg="\n".join(
                f"{f['path']}:{f['line']} [{f['kind']}] {f['detail']}" for f in findings
            ),
        )

    def test_the_gate_is_actually_reading_the_lander_files(self):
        self.assertTrue(gate.LANDERS.is_dir(), gate.LANDERS)
        scanned = [
            p.name
            for p in gate.LANDERS.glob("*.py")
            if p.name not in gate.NON_LANDER_MODULES
        ]
        # 30+ domain landers plus _helpers. If this collapses to a handful, the
        # clean result above stopped meaning anything.
        self.assertGreater(len(scanned), 25, scanned)
        self.assertIn("student_lander.py", scanned)

    def test_every_lander_actually_uses_the_contract(self):
        """Clean could also mean "nobody records row failures at all"."""
        adopters = [
            p.name
            for p in gate.LANDERS.glob("*_lander.py")
            if "record_row_error(" in p.read_text(encoding="utf-8")
        ]
        self.assertGreater(len(adopters), 25, adopters)


if __name__ == "__main__":
    unittest.main()
