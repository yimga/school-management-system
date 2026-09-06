"""Tests for scan_unrestored_flush_testcase.

The cases that matter are the must-FIRE ones (a flushing class with no restore),
the must-stay-SILENT ones that would otherwise make this gate noisy enough to
switch off (a locally shadowed base name, an inherited cure), and the live-tree
seal, which is what turns this from a script into a ratchet.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scan_unrestored_flush_testcase as scanner  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def kinds(source: str) -> list[str]:
    return [f["kind"] for f in scanner.scan_source("sample.py", source)]


class MustFireTests(unittest.TestCase):
    def test_bare_transaction_testcase_is_a_finding(self):
        self.assertEqual(
            kinds("class A(TransactionTestCase):\n    pass\n"), ["unrestored-flush"]
        )

    def test_live_server_testcase_flushes_too(self):
        """It is a TransactionTestCase subclass, and one was sitting in apps/compliance.

        A search for the obvious base class does not find it, which is exactly
        how it survived the 2026-09-03 conversion pass.
        """
        self.assertEqual(
            kinds("class A(LiveServerTestCase):\n    pass\n"), ["unrestored-flush"]
        )

    def test_multi_line_base_list_is_still_seen(self):
        """A regex anchored on the class line misses this shape entirely."""
        self.assertEqual(
            kinds("class A(\n    TransactionTestCase,\n):\n    pass\n"),
            ["unrestored-flush"],
        )

    def test_marker_without_a_real_reason_is_a_finding(self):
        self.assertEqual(
            kinds("class A(TransactionTestCase):  # seed-flush-allow: x\n    pass\n"),
            ["allow-marker-without-reason"],
        )

    def test_marker_on_a_class_that_does_not_flush_is_a_finding(self):
        """An excuse must not outlive the thing it excused."""
        self.assertEqual(
            kinds(
                "# seed-flush-allow: reason that no longer applies here\n"
                "class A(TestCase):\n    pass\n"
            ),
            ["stale-allow-marker"],
        )


class MustStaySilentTests(unittest.TestCase):
    def test_mixin_satisfies_the_rule(self):
        self.assertEqual(
            kinds("class A(RestoresSeedCatalogMixin, TransactionTestCase):\n    pass\n"),
            [],
        )

    def test_plain_testcase_does_not_flush(self):
        self.assertEqual(kinds("class A(TestCase):\n    pass\n"), [])

    def test_reviewed_marker_excuses_the_class(self):
        self.assertEqual(
            kinds(
                "# seed-flush-allow: needs real DDL outside a transaction\n"
                "class A(TransactionTestCase):\n    pass\n"
            ),
            [],
        )

    def test_cure_is_inherited_from_a_local_base(self):
        self.assertEqual(
            kinds(
                "class Base(RestoresSeedCatalogMixin, TransactionTestCase):\n    pass\n"
                "class A(Base):\n    pass\n"
            ),
            [],
        )

    def test_a_locally_shadowed_name_is_not_djangos_class(self):
        """apps/finance/tests/test_payment_phase2.py really does this.

        It defines its own ``class TransactionTestCase(TestCase)`` to test
        transaction models. Matching bases by name without noticing the shadow
        would accuse correct code, which is how a gate gets switched off.
        """
        self.assertEqual(
            kinds(
                "class TransactionTestCase(TestCase):\n    pass\n"
                "class A(TransactionTestCase):\n    pass\n"
            ),
            [],
        )

    def test_unparseable_is_another_gates_job(self):
        self.assertEqual(kinds("class A(:\n"), [])


class LiveTreeTests(unittest.TestCase):
    def test_self_check_passes(self):
        self.assertTrue(scanner.self_check())

    def test_discovery_finds_a_non_empty_corpus(self):
        """A zero over an empty corpus is not a zero.

        This repo has flushing classes; finding no candidate files would mean
        discovery broke, not that the tree is clean.
        """
        self.assertGreater(len(scanner.candidate_files()), 5)

    def test_live_tree_is_clean(self):
        proc = subprocess.run(
            [sys.executable, "scripts/scan_unrestored_flush_testcase.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            "the tree must scan clean; findings:\n%s" % proc.stdout,
        )


if __name__ == "__main__":
    unittest.main()
