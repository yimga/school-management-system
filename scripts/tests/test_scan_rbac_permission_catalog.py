"""Lock the RBAC catalog detector so a green gate keeps meaning something.

A zero-baseline gate is worth exactly what its detector is worth. Once the tree
is clean, a scanner that has stopped detecting anything prints the same
"0 finding(s)" as one that works. These tests pin the shapes it must catch, the
shapes it must stay quiet about, and — the calibration that matters most — that
it still finds real codes and a real catalog in the live tree.

Stdlib only, no Django: this covers the extraction layer.
"""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import scan_rbac_permission_catalog as gate  # noqa: E402


class _TempTree(unittest.TestCase):
    """Run the extractor over a synthetic apps/ tree."""

    tmp_name = "_tmp_rbac_catalog"

    def setUp(self):
        self._tmp = Path(__file__).parent / self.tmp_name
        shutil.rmtree(self._tmp, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def codes(self, source: str, name: str = "views.py") -> list[str]:
        app = self._tmp / "apps" / "demo"
        app.mkdir(parents=True, exist_ok=True)
        (app / name).write_text(source, encoding="utf-8")
        original = gate.REPO_ROOT
        gate.REPO_ROOT = self._tmp
        try:
            return [code for _rel, _line, code in gate.gated_codes()]
        finally:
            gate.REPO_ROOT = original


class TheDetectorFiresTests(_TempTree):
    tmp_name = "_tmp_rbac_catalog_fires"

    def test_a_direct_feature_permission_check_is_a_candidate(self):
        found = self.codes('user.has_feature_permission("thing.code")\n')
        self.assertIn("thing.code", found)

    def test_every_gated_call_shape_is_covered(self):
        shapes = (
            'user.has_feature_permission("a.code")',
            'require_permission("a.code")',
            'permission_access(user, school, ("a.code",))',
            'user_has_permission(user, school, ("a.code",))',
            'enforce_permission_token(user, "a.code", school=school)',
            'check_permission_token(user, "a.code")',
            'feature_permission_allowed(user, "a.code")',
        )
        for shape in shapes:
            with self.subTest(shape=shape):
                self.assertIn("a.code", self.codes(shape + "\n"))

    def test_a_three_segment_code_is_a_candidate(self):
        """athletics.eligibility.override is a real code shape."""
        found = self.codes('user.has_feature_permission("athletics.eligibility.override")\n')
        self.assertIn("athletics.eligibility.override", found)

    def test_the_offline_sync_shape_that_shipped_broken_is_caught(self):
        """The exact call that denied every mobile teacher."""
        source = (
            "if school and not enforce_permission_token(\n"
            '    request.user, "grade.submit", school=school\n'
            "):\n"
            "    pass\n"
        )
        self.assertIn("grade.submit", self.codes(source))


class TheDetectorStaysSilentTests(_TempTree):
    """Every one of these was a false positive during development."""

    tmp_name = "_tmp_rbac_catalog_quiet"

    def test_django_builtin_permissions_are_not_our_codes(self):
        """permission_required is overloaded across both permission systems."""
        for code in ("people.view_teacherprofile", "academics.add_classroom", "auth.add_user"):
            with self.subTest(code=code):
                self.assertEqual(self.codes(f'permission_required("{code}")\n'), [])

    def test_the_marker_excuses_the_same_line(self):
        found = self.codes(
            'user.has_feature_permission("thing.code")  # rbac-code-allow: external\n'
        )
        self.assertEqual(found, [])

    def test_the_marker_excuses_the_line_above(self):
        source = (
            "# rbac-code-allow: external\n"
            'user.has_feature_permission("thing.code")\n'
        )
        self.assertEqual(self.codes(source), [])

    def test_tests_are_not_scanned(self):
        app = self._tmp / "apps" / "demo" / "tests"
        app.mkdir(parents=True, exist_ok=True)
        (app / "test_x.py").write_text(
            'user.has_feature_permission("thing.code")\n', encoding="utf-8"
        )
        original = gate.REPO_ROOT
        gate.REPO_ROOT = self._tmp
        try:
            self.assertEqual(list(gate.gated_codes()), [])
        finally:
            gate.REPO_ROOT = original

    def test_an_unrelated_call_is_not_scanned(self):
        self.assertEqual(self.codes('logger.info("some.dotted.thing")\n'), [])

    def test_the_argument_span_does_not_bleed_into_the_next_call(self):
        """A code from a LATER, exempted call must not be attributed to this one."""
        source = (
            'user.has_feature_permission("first.code")\n'
            'logger.info("second.code")\n'
        )
        found = self.codes(source)
        self.assertIn("first.code", found)
        self.assertNotIn("second.code", found)


class TheCatalogIsReadFromMigrationsTests(unittest.TestCase):
    """The catalog side of the comparison must keep working too."""

    def test_the_live_catalog_is_populated(self):
        codes = gate.catalog_codes()
        self.assertGreater(
            len(codes),
            30,
            "the catalog reader stopped finding Permission definitions — "
            "every gated code would then report as a finding",
        )

    def test_known_seeded_codes_are_present(self):
        codes = gate.catalog_codes()
        for expected in ("settings.manage", "grades.enter", "identity.reset_credentials"):
            with self.subTest(code=expected):
                self.assertIn(expected, codes)

    def test_the_codes_repaired_in_0058_are_now_catalogued(self):
        """Regression pin: these four denied everyone but a superadmin."""
        codes = gate.catalog_codes()
        for expected in (
            "grade.submit",
            "attendance.mark",
            "finance.access",
            "marketplace.view",
        ):
            with self.subTest(code=expected):
                self.assertIn(expected, codes)


class TheLiveTreeIsCleanTests(unittest.TestCase):
    """Calibration: proves 0 means clean, not that the scanner found nothing."""

    def test_the_repo_still_has_gated_codes_to_check(self):
        found = gate.gated_codes()
        self.assertGreater(
            len(found),
            20,
            "the extractor stopped finding gated codes — a silently dead gate",
        )

    def test_the_tree_has_no_ungranted_codes(self):
        self.assertEqual(
            gate.findings(),
            [],
            "a permission code is gated on but never seeded — no role can hold it",
        )


if __name__ == "__main__":
    unittest.main()
