"""Tests for scan_refusal_only_assertions.

The must-FIRE cases are a refusal-only authorization test. The must-stay-SILENT
ones matter as much: this gate rides pre-push, and one that accuses a correct
test is one somebody switches off. The live-tree cases are what turn it from a
script into a ratchet.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scan_refusal_only_assertions as scanner  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def keys(source: str) -> list[str]:
    return [f["key"] for f in scanner.scan_source("s.py", source)]


class MustFireTests(unittest.TestCase):
    def test_sole_refusal_assertion(self):
        self.assertEqual(
            len(keys("def test_cross_tenant_blocked(self):\n"
                     "    self.assertEqual(r.status_code, 403)\n")),
            1,
        )

    def test_membership_form_is_still_status_only(self):
        self.assertEqual(
            len(keys("def test_scope_denied(self):\n"
                     "    self.assertIn(r.status_code, (401, 403))\n")),
            1,
        )

    def test_a_redirect_counts_as_a_refusal_shape(self):
        """A 302 on a privileged view here is usually /mfa/setup/ or the login.

        Same "the request never arrived" failure, different number -- so a test
        asserting only 302 is exactly as unable to fail as one asserting 403.
        """
        self.assertEqual(
            len(keys("def test_tenant_isolation(self):\n"
                     "    self.assertEqual(r.status_code, 302)\n")),
            1,
        )


class MustStaySilentTests(unittest.TestCase):
    def test_asserting_the_effect_is_the_cure(self):
        self.assertEqual(
            keys("def test_cross_tenant_blocked(self):\n"
                 "    self.assertEqual(r.status_code, 403)\n"
                 "    self.assertFalse(Payment.objects.exists())\n"),
            [],
        )

    def test_a_success_code_is_not_a_refusal(self):
        self.assertEqual(
            keys("def test_tenant_scope_ok(self):\n"
                 "    self.assertEqual(r.status_code, 200)\n"),
            [],
        )

    def test_assert_contains_checks_content_too(self):
        self.assertEqual(
            keys("def test_cross_tenant_blocked(self):\n"
                 "    self.assertContains(r, 'nope', status_code=403)\n"),
            [],
        )

    def test_a_name_with_no_authorization_claim_is_not_reported(self):
        """Most refusal-only tests are honest tests of an unambiguous path."""
        self.assertEqual(
            keys("def test_corrupt_gzip_body_is_a_400(self):\n"
                 "    self.assertEqual(r.status_code, 400)\n"),
            [],
        )

    def test_a_bare_assert_statement_counts_as_state(self):
        self.assertEqual(
            keys("def test_cross_tenant_blocked(self):\n"
                 "    assert r.status_code == 403\n"),
            [],
        )

    def test_a_helper_is_not_a_test(self):
        self.assertEqual(
            keys("def helper_cross_tenant_blocked(self):\n"
                 "    self.assertEqual(r.status_code, 403)\n"),
            [],
        )

    def test_unparseable_is_another_gates_job(self):
        self.assertEqual(keys("def test_x(:\n"), [])


class KeyIdentityTests(unittest.TestCase):
    def test_same_test_name_in_two_classes_yields_two_keys(self):
        """A file::name key silently merges these, and one goes un-ratcheted.

        apps/finance/tests/test_invoicing_is_school_scoped_2026_09_02.py really
        does define the same test name in two classes; it is why the baseline
        wrote 249 entries and read back 248.
        """
        got = keys(
            "class A:\n"
            "    def test_tenant_blocked(self):\n"
            "        self.assertEqual(r.status_code, 403)\n"
            "class B:\n"
            "    def test_tenant_blocked(self):\n"
            "        self.assertEqual(r.status_code, 403)\n"
        )
        self.assertEqual(len(got), 2)
        self.assertEqual(len(set(got)), 2, "keys collided: %r" % got)


class LiveTreeTests(unittest.TestCase):
    def test_self_check_passes(self):
        self.assertTrue(scanner.self_check())

    def test_discovery_finds_a_non_empty_corpus(self):
        """A zero over an empty corpus is not a zero."""
        self.assertGreater(len(scanner.candidate_files()), 100)

    def test_baseline_matches_the_tree(self):
        proc = subprocess.run(
            [sys.executable, "scripts/scan_refusal_only_assertions.py", "--compare"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, "new findings:\n%s" % proc.stdout)

    def test_baseline_count_and_keys_agree(self):
        """The written count and the readable keys must not disagree."""
        payload = json.loads(scanner.BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["count"], len(payload["keys"]))
        self.assertEqual(len(payload["keys"]), len(set(payload["keys"])))

    def test_a_bare_run_never_writes_the_baseline(self):
        """Several scanners here launder findings this way; this one must not."""
        before = scanner.BASELINE_PATH.read_bytes()
        subprocess.run(
            [sys.executable, "scripts/scan_refusal_only_assertions.py"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(before, scanner.BASELINE_PATH.read_bytes())


if __name__ == "__main__":
    unittest.main()
