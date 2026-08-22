"""Stdlib tests for scripts/scan_raw_token_in_ui.py."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scan_raw_token_in_ui.py"
_SPEC = importlib.util.spec_from_file_location("scan_raw_token_in_ui", _SCRIPT)
assert _SPEC and _SPEC.loader
scanner = importlib.util.module_from_spec(_SPEC)
sys.modules["scan_raw_token_in_ui"] = scanner
_SPEC.loader.exec_module(scanner)


def _template(body: str) -> Path:
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    )
    handle.write(body)
    handle.close()
    return Path(handle.name)


def _module(body: str) -> Path:
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8"
    )
    handle.write(body)
    handle.close()
    return Path(handle.name)


class CutSeparatorTests(unittest.TestCase):
    def test_underscore_cut_is_a_finding(self):
        path = _template('<span>{{ state|cut:"_" }}</span>\n')
        findings = scanner.scan_template(path)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "cut_separator")
        self.assertEqual(findings[0]["separator"], "_")

    def test_hyphen_cut_is_a_finding(self):
        path = _template("<span>{{ preset|cut:'-' }}</span>\n")
        self.assertEqual(len(scanner.scan_template(path)), 1)

    def test_spacing_and_quote_style_do_not_hide_it(self):
        path = _template("<span>{{ x | cut : \"_\" }}</span>\n")
        self.assertEqual(len(scanner.scan_template(path)), 1)

    def test_cutting_a_non_separator_is_not_a_finding(self):
        # Cutting a currency sign or a space is a different, legitimate use.
        path = _template('<span>{{ amount|cut:"$" }}{{ s|cut:" " }}</span>\n')
        self.assertEqual(scanner.scan_template(path), [])

    def test_humanize_token_is_not_a_finding(self):
        path = _template("<span>{{ state|humanize_token }}</span>\n")
        self.assertEqual(scanner.scan_template(path), [])

    def test_allow_marker_on_the_same_line_silences_it(self):
        path = _template(
            '<span>{{ x|cut:"_" }}</span>{# raw-token-allow: reviewed #}\n'
        )
        self.assertEqual(scanner.scan_template(path), [])

    def test_allow_marker_on_the_line_above_silences_it(self):
        path = _template(
            "{# raw-token-allow: reviewed #}\n" '<span>{{ x|cut:"_" }}</span>\n'
        )
        self.assertEqual(scanner.scan_template(path), [])

    def test_a_bare_allow_word_with_no_reason_does_not_silence_it(self):
        path = _template('<span>{{ x|cut:"_" }}</span>{# raw-token-allow: #}\n')
        self.assertEqual(len(scanner.scan_template(path)), 1)

    def test_line_number_is_reported(self):
        path = _template('a\nb\n<span>{{ x|cut:"_" }}</span>\n')
        self.assertEqual(scanner.scan_template(path)[0]["line"], 3)


class VocabularyTests(unittest.TestCase):
    SOURCE_OK = (
        'A = "alpha"\n'
        'B = "beta"\n'
        "MEMBERS = (A, B)\n"
        "LABELS = {A: _('Alpha'), B: _('Beta')}\n"
    )

    def test_fully_labelled_vocabulary_is_clean(self):
        path = _module(self.SOURCE_OK)
        self.assertEqual(scanner.scan_vocabulary(path, "MEMBERS", "LABELS"), [])

    def test_member_without_a_label_is_a_finding(self):
        path = _module(
            'A = "alpha"\n'
            'B = "beta"\n'
            "MEMBERS = (A, B)\n"
            "LABELS = {A: _('Alpha')}\n"
        )
        findings = scanner.scan_vocabulary(path, "MEMBERS", "LABELS")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "unlabelled_vocabulary_member")
        self.assertEqual(findings[0]["member"], "beta")

    def test_label_for_a_removed_member_is_a_finding(self):
        path = _module(
            'A = "alpha"\n'
            "MEMBERS = (A,)\n"
            "LABELS = {A: _('Alpha'), 'gone': _('Gone')}\n"
        )
        findings = scanner.scan_vocabulary(path, "MEMBERS", "LABELS")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "orphan_vocabulary_label")
        self.assertEqual(findings[0]["member"], "gone")

    def test_plain_string_members_resolve_without_constants(self):
        path = _module(
            'MEMBERS = ("one", "two")\n' "LABELS = {'one': 'One'}\n"
        )
        findings = scanner.scan_vocabulary(path, "MEMBERS", "LABELS")
        self.assertEqual([f["member"] for f in findings], ["two"])

    def test_annotated_assignment_is_read(self):
        path = _module(
            'MEMBERS: tuple[str, ...] = ("one",)\n'
            "LABELS: dict[str, str] = {'one': 'One'}\n"
        )
        self.assertEqual(scanner.scan_vocabulary(path, "MEMBERS", "LABELS"), [])

    def test_renamed_constant_is_reported_not_silently_skipped(self):
        path = _module('MEMBERS = ("one",)\n')
        findings = scanner.scan_vocabulary(path, "MEMBERS", "LABELS")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "vocabulary_constant_missing")

    def test_unparseable_module_is_not_a_finding(self):
        # verify_python_files_parse owns that report; saying it twice buries it.
        path = _module("def broken(:\n")
        self.assertEqual(scanner.scan_vocabulary(path, "MEMBERS", "LABELS"), [])


class LiveTreeTests(unittest.TestCase):
    def test_registered_vocabularies_exist_and_are_fully_labelled(self):
        for rel, (members, labels) in scanner.VOCABULARIES.items():
            path = scanner.ROOT / rel
            self.assertTrue(path.is_file(), f"{rel} is registered but missing")
            self.assertEqual(
                scanner.scan_vocabulary(path, members, labels),
                [],
                f"{rel} has an unlabelled member or an orphan label",
            )

    def test_repository_scans_clean(self):
        findings = scanner.scan_repository()
        self.assertEqual(
            findings,
            [],
            "raw-token-in-ui is zero-tolerance; findings: "
            + "; ".join(f"{f['path']}:{f['line']} {f['kind']}" for f in findings),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
