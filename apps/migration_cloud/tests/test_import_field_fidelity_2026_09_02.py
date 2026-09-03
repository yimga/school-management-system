"""A real school's hand-kept workbook, run against the intake -- field by field.

Four defects were measured on 2026-09-02 by walking one tenant's actual upload
set through the engine, and each test here is one of them, generalized:

1. ``subjects.xlsx`` carried a CATEGORY column (Professional/General) that maps
   1:1 onto ``Subject.Category`` -- and the academics lander read only
   name/code/credits, so every category fell to residual capture, invisible in
   the catalog. (The canonical header set had already been extended with
   ``category`` for exactly this file shape; the lander never caught up.)
2. A staff directory headed its phone column ``TELEPHONE NUMBER``; the staff
   phone synonyms had ``telephone`` but no two-word forms, so 50 phones dropped.
3. The same directory's role column was headed ``POST / FUNCTION / Role`` and
   its people column just ``NAME`` -- a compound header matched nothing whole,
   and the name fallback read only ``full_name``.
4. The workbook opened with a merged school-name banner above the real header
   row, so TSV line one -- the header row downstream -- was the banner.

Role labels from the same directory: compound cells ("BURSAR/ PARTNER") now
resolve when every role-naming segment agrees, and stay HELD when two different
roles share one cell, because picking either would grant a privilege the sheet
did not clearly state.
"""

from __future__ import annotations

import io

from django.test import SimpleTestCase, TestCase

from apps.academics.models import Subject
from apps.accounts.models import User
from apps.migration_cloud.landers.academics_lander import AcademicsLander, _resolve_category
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.staff_lander import StaffLander, _staff_field_from_row
from apps.migration_cloud.staff_role_map import (
    ROLE_FORBIDDEN,
    ROLE_UNMAPPED,
    resolve_staff_role,
    unresolvable_staff_role,
)
from apps.migration_cloud.xlsx_explode import _trim_banner_rows, explode_workbook
from apps.people.models import TeacherProfile
from apps.schools.models import School


class SubjectCategoryResolverTests(SimpleTestCase):
    def test_choice_labels_and_values_both_resolve(self):
        self.assertEqual(_resolve_category("Professional", Subject), "PROFESSIONAL")
        self.assertEqual(_resolve_category("GENERAL", Subject), "GENERAL")
        self.assertEqual(_resolve_category(" professional ", Subject), "PROFESSIONAL")

    def test_unrecognized_label_is_never_a_guess(self):
        self.assertIsNone(_resolve_category("Vocational-ish", Subject))
        self.assertIsNone(_resolve_category("", Subject))
        self.assertIsNone(_resolve_category(None, Subject))


class CompoundRoleCellTests(SimpleTestCase):
    def test_measured_directory_titles_now_resolve(self):
        self.assertEqual(resolve_staff_role("DEAN OF STUDIES"), User.Role.DEAN)
        self.assertEqual(
            resolve_staff_role("SENIOR DISCIPLINE MASTER"), User.Role.DISCIPLINE_MASTER
        )
        self.assertEqual(
            resolve_staff_role("SCHOOL SYSTEM ADMINISTRATOR/IT"), User.Role.IT_ADMIN
        )
        for label in ("DEAN OF STUDIES", "SENIOR DISCIPLINE MASTER"):
            self.assertIsNone(unresolvable_staff_role(label), label)

    def test_compound_cell_resolves_when_segments_agree(self):
        self.assertEqual(resolve_staff_role("BURSAR/ PARTNER"), User.Role.BURSAR)
        self.assertIsNone(unresolvable_staff_role("BURSAR/ PARTNER"))
        self.assertEqual(resolve_staff_role("TEACHER /DRIVER"), User.Role.TEACHER)
        self.assertIsNone(unresolvable_staff_role("TEACHER /DRIVER"))

    def test_two_roles_in_one_cell_stay_held(self):
        # SECRETARY vs IT_ADMIN: the sheet did not say which. Held, not chosen.
        self.assertEqual(
            unresolvable_staff_role("ADMINISTRATIVE ASSISTANT / IT"), ROLE_UNMAPPED
        )

    def test_forbidden_segment_forbids_the_whole_cell(self):
        self.assertEqual(unresolvable_staff_role("STUDENT/TEACHER"), ROLE_FORBIDDEN)

    def test_plainly_unmappable_support_titles_stay_held(self):
        for label in ("DRIVER", "SECURITY", "COORDINATOR"):
            self.assertEqual(unresolvable_staff_role(label), ROLE_UNMAPPED, label)


class StaffHeaderResolutionTests(SimpleTestCase):
    def test_compound_header_segments_reach_the_field(self):
        row = {"post / function / role": "PRINCIPAL"}
        self.assertEqual(_staff_field_from_row(row, "role"), "PRINCIPAL")

    def test_two_word_telephone_header_reaches_phone(self):
        row = {"telephone number": "677 11 22 33"}
        self.assertEqual(_staff_field_from_row(row, "phone"), "677 11 22 33")

    def test_spaces_alone_never_split_a_header(self):
        # "administrative assistant" must not match an "assistant" field
        # one word at a time -- only strong delimiters segment.
        row = {"administrative assistant": "x"}
        self.assertEqual(_staff_field_from_row(row, "role"), "")


class BannerRowTrimTests(SimpleTestCase):
    def test_leading_single_cell_banners_are_dropped(self):
        rows = [
            ["SOME TECHNICAL HIGH SCHOOL", "", "", ""],
            ["TELEPHONE DIRECTORY FOR 2026/2027", "", "", ""],
            ["NAME", "POST / FUNCTION / Role", "SPECIALTY", "TELEPHONE NUMBER"],
            ["JANE DOE", "TEACHER", "WELDING", "677000000"],
        ]
        trimmed = _trim_banner_rows(rows)
        self.assertEqual(trimmed[0][0], "NAME")
        self.assertEqual(len(trimmed), 2)

    def test_header_first_sheet_is_untouched(self):
        rows = [["NAME", "ROLE"], ["JANE", "TEACHER"]]
        self.assertEqual(_trim_banner_rows(rows), rows)

    def test_single_column_sheet_is_untouched(self):
        rows = [["title"], ["one"], ["two"]]
        self.assertEqual(_trim_banner_rows(rows), rows)

    def test_end_to_end_through_a_real_workbook(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl unavailable")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["A SCHOOL NAME BANNER"])
        ws.append(["A SUBTITLE LINE"])
        ws.append(["NAME", "ROLE", "TELEPHONE NUMBER"])
        ws.append(["JANE DOE", "TEACHER", "677000000"])
        buf = io.BytesIO()
        wb.save(buf)
        sheets = explode_workbook(buf.getvalue())
        self.assertEqual(len(sheets), 1)
        first_line = sheets[0][1].decode("utf-8").splitlines()[0]
        self.assertTrue(first_line.startswith("NAME\t"), first_line)


class AcademicsCategoryLandingTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Field Fidelity School",
            slug="field-fidelity",
            subdomain="fieldfidelity",
            is_active=True,
            country_code="CM",
        )
        self.ctx = LanderContext(
            school=self.school, bundle_id=1, artifact_id=1, dry_run=False, schema_name=""
        )

    def _land(self, row):
        return AcademicsLander().land(canonical_rows=iter([dict(row)]), ctx=self.ctx)

    def test_category_column_lands_on_the_subject(self):
        res = self._land({"title": "WORKSHOP PRACTICE", "category": "Professional"})
        self.assertEqual(res.created, 1, res.errors)
        subj = Subject.objects.get(school=self.school, name="WORKSHOP PRACTICE")
        self.assertEqual(subj.category, Subject.Category.PROFESSIONAL)

    def test_reupload_backfills_a_default_category_only(self):
        Subject.objects.create(school=self.school, name="LITERATURE")
        self._land({"title": "LITERATURE", "category": "General"})
        subj = Subject.objects.get(school=self.school, name="LITERATURE")
        self.assertEqual(subj.category, Subject.Category.GENERAL)

    def test_a_deliberate_category_outranks_the_import(self):
        Subject.objects.create(
            school=self.school, name="DRAWING", category=Subject.Category.PROFESSIONAL
        )
        res = self._land({"title": "DRAWING", "category": "General"})
        subj = Subject.objects.get(school=self.school, name="DRAWING")
        self.assertEqual(subj.category, Subject.Category.PROFESSIONAL)
        self.assertTrue(
            any("kept category" in str(n) for n in getattr(res, "notes", []) or []),
            "the disagreement must be reported, not silent",
        )

    def test_unknown_label_lands_the_subject_and_says_so(self):
        res = self._land({"title": "FORGE WORK", "category": "Vocational-ish"})
        subj = Subject.objects.get(school=self.school, name="FORGE WORK")
        self.assertEqual(subj.category, Subject.Category.OTHER)
        self.assertTrue(
            any("matches no Subject.Category" in str(n) for n in getattr(res, "notes", []) or []),
            "an unread label must be reported, not silent",
        )


class DirectoryShapedStaffRowTests(TestCase):
    """The measured directory row shape, end to end through the staff lander."""

    def setUp(self):
        self.school = School.objects.create(
            name="Directory School",
            slug="directory-school",
            subdomain="directoryschool",
            is_active=True,
            country_code="CM",
        )
        self.ctx = LanderContext(
            school=self.school, bundle_id=1, artifact_id=1, dry_run=False, schema_name=""
        )

    def test_name_post_and_telephone_headers_land_a_complete_teacher(self):
        res = StaffLander().land(
            canonical_rows=iter(
                [
                    {
                        "name": "FRU JANE ANDIN",
                        "post / function / role": "PRINCIPAL",
                        "telephone number": "677 11 22 33",
                    }
                ]
            ),
            ctx=self.ctx,
        )
        self.assertEqual(res.quarantined, 0, res.errors)
        profile = TeacherProfile.objects.get(school=self.school)
        self.assertEqual(profile.phone, "677 11 22 33")
        self.assertEqual(profile.user.role, User.Role.PRINCIPAL)
        self.assertNotEqual(profile.user.first_name, "")
        self.assertNotEqual(profile.user.last_name, "")
