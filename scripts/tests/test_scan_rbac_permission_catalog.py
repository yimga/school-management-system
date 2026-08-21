"""Lock the RBAC catalog detector so a green gate keeps meaning something.

A zero-baseline gate is worth exactly what its detector is worth. Once the tree
is clean, a scanner that has stopped detecting anything prints the same
"0 finding(s)" as one that works. These tests pin the shapes it must catch, the
shapes it must stay quiet about, and — the calibration that matters most — that
it still finds real codes and a real catalog in the live tree.

The 2026-08-21 re-audit is why several of these exist. The first version of the
gate keyed on ``name(``, which three real call shapes never look like; between
them they hid four gated codes, two of which were genuine orphans.

Stdlib only, no Django: this covers the extraction layer.
"""

from __future__ import annotations

import re
import shutil
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import scan_rbac_permission_catalog as gate  # noqa: E402

NL = "\n"


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
        found = self.codes('user.has_feature_permission("thing.code")' + NL)
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
                self.assertIn("a.code", self.codes(shape + NL))

    def test_a_three_segment_code_is_a_candidate(self):
        """athletics.eligibility.override is a real code shape."""
        found = self.codes(
            'user.has_feature_permission("athletics.eligibility.override")' + NL
        )
        self.assertIn("athletics.eligibility.override", found)

    def test_the_offline_sync_shape_that_shipped_broken_is_caught(self):
        """The exact call that denied every mobile teacher."""
        source = (
            "if school and not enforce_permission_token(" + NL
            + '    request.user, "grade.submit", school=school' + NL
            + "):" + NL
            + "    pass" + NL
        )
        self.assertIn("grade.submit", self.codes(source))


class TheShapesTheFirstGateMissedTests(_TempTree):
    """Live blind spots found when re-auditing the gate on 2026-08-21."""

    tmp_name = "_tmp_rbac_catalog_missed"

    def test_the_getattr_idiom_is_a_candidate(self):
        """The method name is a STRING here, so it is never followed by "(".

        This shape hid api_center.manage, cahier.verify, discipline.refer and
        finance.view_invoice from the gate completely.
        """
        source = (
            'return getattr(user, "has_feature_permission", lambda _: False)'
            '("discipline.refer")' + NL
        )
        self.assertIn("discipline.refer", self.codes(source))

    def test_the_getattr_idiom_split_across_lines_is_a_candidate(self):
        """The finance inbox wrote it across three lines."""
        source = (
            "can_see = user.is_superuser or getattr(" + NL
            + '    user, "has_feature_permission", lambda _: False' + NL
            + ')("finance.view_invoice")' + NL
        )
        self.assertIn("finance.view_invoice", self.codes(source))

    def test_a_private_wrapper_is_a_candidate(self):
        """action_engine.py wraps the resolver as ``_has_feature_permission``.

        A word boundary does not match between "_" and "h", so the four codes
        that MOTIVATED this gate were invisible to its first version.
        """
        found = self.codes('_has_feature_permission(user, "marketplace.view")' + NL)
        self.assertIn("marketplace.view", found)

    def test_the_drf_rebac_class_argument_is_a_candidate(self):
        found = self.codes(
            'return [IsAuthenticated(), RebacPermission("finance.view")]' + NL
        )
        self.assertIn("finance.view", found)


class TemplateGatesAreCoveredTests(unittest.TestCase):
    """``{% if user|has_feature_permission:"code" %}`` hides a panel silently."""

    def setUp(self):
        self._tmp = Path(__file__).parent / "_tmp_rbac_catalog_tpl"
        shutil.rmtree(self._tmp, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _codes(self, source: str):
        root = self._tmp / "templates"
        root.mkdir(parents=True, exist_ok=True)
        (root / "page.html").write_text(source, encoding="utf-8")
        original = gate.REPO_ROOT
        gate.REPO_ROOT = self._tmp
        try:
            return [c for _rel, _line, c in gate.gated_codes()]
        finally:
            gate.REPO_ROOT = original

    def test_the_template_filter_is_a_candidate(self):
        found = self._codes(
            '{% if user|has_feature_permission:"portal.forums" %}ok{% endif %}' + NL
        )
        self.assertIn("portal.forums", found)

    def test_single_quotes_work_too(self):
        found = self._codes(
            "{% if user|has_feature_permission:'portal.video' %}ok{% endif %}" + NL
        )
        self.assertIn("portal.video", found)

    def test_the_live_templates_still_yield_candidates(self):
        """Calibration: the template arm must not silently stop finding things."""
        found = [c for rel, _l, c in gate.gated_codes() if rel.endswith(".html")]
        self.assertGreater(
            len(found), 0, "the template arm of the gate stopped finding anything"
        )


class TheGroupedPickerStaysCompleteTests(unittest.TestCase):
    """A seeded code an owner cannot find is only half-granted.

    ``_rbac_permissions_by_group`` drops anything ungrouped into an "Other"
    bucket, so the code is still grantable — but sixteen codes in one unlabelled
    pile is a picker nobody can use. This keeps the two lists honest.
    """

    def _grouped(self) -> set[str]:
        src = (REPO_ROOT / "apps" / "accounts" / "permissions.py").read_text(
            encoding="utf-8"
        )
        block = re.search(r"PERMISSION_GROUPS\s*=\s*\{(.*?)\n\}", src, re.S)
        self.assertIsNotNone(block, "PERMISSION_GROUPS block not found")
        return set(re.findall(r'"([a-z_]+(?:\.[a-z_]+)+)"', block.group(1)))

    def test_every_catalog_code_has_a_group(self):
        missing = sorted(gate.catalog_codes() - self._grouped())
        self.assertEqual(
            missing, [], f"seeded but unfindable in the RBAC picker: {missing}"
        )

    def test_no_group_lists_a_code_that_does_not_exist(self):
        phantom = sorted(self._grouped() - gate.catalog_codes())
        self.assertEqual(
            phantom, [], f"picker offers codes that were never seeded: {phantom}"
        )


class TheDetectorStaysSilentTests(_TempTree):
    """Every one of these was a false positive during development."""

    tmp_name = "_tmp_rbac_catalog_quiet"

    def test_django_builtin_permissions_are_not_our_codes(self):
        """permission_required is overloaded across both permission systems."""
        for code in (
            "people.view_teacherprofile",
            "academics.add_classroom",
            "auth.add_user",
        ):
            with self.subTest(code=code):
                self.assertEqual(self.codes(f'permission_required("{code}")' + NL), [])

    def test_the_marker_excuses_the_same_line(self):
        found = self.codes(
            'user.has_feature_permission("thing.code")  # rbac-code-allow: external' + NL
        )
        self.assertEqual(found, [])

    def test_the_marker_excuses_the_line_above(self):
        source = (
            "# rbac-code-allow: external" + NL
            + 'user.has_feature_permission("thing.code")' + NL
        )
        self.assertEqual(self.codes(source), [])

    def test_tests_are_not_scanned(self):
        app = self._tmp / "apps" / "demo" / "tests"
        app.mkdir(parents=True, exist_ok=True)
        (app / "test_x.py").write_text(
            'user.has_feature_permission("thing.code")' + NL, encoding="utf-8"
        )
        original = gate.REPO_ROOT
        gate.REPO_ROOT = self._tmp
        try:
            self.assertEqual(list(gate.gated_codes()), [])
        finally:
            gate.REPO_ROOT = original

    def test_an_unrelated_call_is_not_scanned(self):
        self.assertEqual(self.codes('logger.info("some.dotted.thing")' + NL), [])

    def test_the_argument_span_does_not_bleed_into_the_next_call(self):
        """A code from a LATER call must not be attributed to this one."""
        source = (
            'user.has_feature_permission("first.code")' + NL
            + 'logger.info("second.code")' + NL
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
        for expected in (
            "settings.manage",
            "grades.enter",
            "identity.reset_credentials",
        ):
            with self.subTest(code=expected):
                self.assertIn(expected, codes)

    def test_the_catalog_reads_the_get_or_create_kwarg_form(self):
        """0018/0019 seed via ``get_or_create(code="...")``, not a tuple.

        Reading only the tuple form under-reported the catalog by two, which
        would flag a correctly-seeded code the moment anyone gated on it.
        """
        codes = gate.catalog_codes()
        self.assertIn("cahier.verify", codes)
        self.assertIn("api_center.manage", codes)

    def test_the_codes_repaired_in_0058_and_0059_are_catalogued(self):
        """Regression pin: each of these denied everyone but a superadmin."""
        codes = gate.catalog_codes()
        for expected in (
            "grade.submit",
            "attendance.mark",
            "finance.access",
            "marketplace.view",
            "discipline.refer",
            "finance.view_invoice",
        ):
            with self.subTest(code=expected):
                self.assertIn(expected, codes)


class TheLiveTreeIsCleanTests(unittest.TestCase):
    """Calibration: proves 0 means clean, not that the scanner found nothing."""

    def test_the_repo_still_has_gated_codes_to_check(self):
        found = gate.gated_codes()
        self.assertGreater(
            len(found),
            100,
            "the extractor stopped finding gated codes — a silently dead gate",
        )

    def test_the_private_wrapper_call_sites_are_seen(self):
        """The four codes that motivated this gate live behind ``_has_...``.

        If this regresses the gate goes quiet about exactly the file it was
        built for, while still reporting a healthy-looking total.
        """
        seen = {
            code
            for rel, _l, code in gate.gated_codes()
            if rel.endswith("platform_runtime/action_engine.py")
        }
        for code in (
            "finance.access",
            "finance.view_dashboard",
            "marketplace.view",
            "reports.view",
        ):
            with self.subTest(code=code):
                self.assertIn(code, seen)

    def test_the_tree_has_no_ungranted_codes(self):
        self.assertEqual(
            gate.findings(),
            [],
            "a permission code is gated on but never seeded — no role can hold it",
        )


if __name__ == "__main__":
    unittest.main()
