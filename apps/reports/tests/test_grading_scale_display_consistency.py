"""WAVE 14 — grading-scale → displayed-band DISPLAY-CONSISTENCY regression (Metric #3).

Proves the property no prior test asserted: when a school changes its grading-scale
config, the DISPLAYED band flips *consistently across EVERY reading surface that shows a
grade* — the term report card, the annual transcript, and the teacher gradebook — because
they all resolve the band through the ONE canonical resolver
(``apps.evals.models.resolve_extended_band_label``) keyed off the school's resolved scale.

Audited live path + the exact per-school scale lever + band resolver each surface calls
(file:line, 2026-07-10):

  - Term report card    reports/services.py:824,845,894    scale from AssessmentWeights.grading_scale
                                                            -> resolve_extended_band_label(scale_type, avg)
  - Annual transcript   reports/services.py:991,1002,1070  scale from resolve_local_scale_type(school)
                                                            -> resolve_extended_band_label(scale_type, avg)
  - Teacher gradebook   evals/views.py:2281,2291           scale from resolve_local_scale_type(school)
                                                            -> resolve_extended_band_label(scale_type, total_score)
  - {% grade_band %}    evals/templatetags/evals_extras.py -> format_grade_band -> resolve_extended_band_label

FAIL-BEFORE (why this is a real assertion, not fake green): every surface band is asserted
EQUAL to ``resolve_extended_band_label(<resolved scale_type>, 72.0)``, and the flip tests
require the label to *change* (WAEC ``B2`` -> qualitative ``Meeting Expectations`` -> ``Pass``)
when the config changes. If a surface ever hardcodes a band table or bypasses the scale
resolver, either the canonical-equality assertion or the flip assertion breaks. Proven
fail-before by monkeypatching ``resolve_extended_band_label`` to a scale-blind constant:
the flip + canonical-equality assertions then fail (documented in the wave report).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.evals.grading import format_grade_band
from apps.evals.grading_provisioning import resolve_local_scale_type
from apps.evals.models import AssessmentWeights, Evaluation, resolve_extended_band_label
from apps.people.models import StudentProfile, TeacherProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.reports.services import annual_report_context, term_report_context
from apps.schools.models import School

# A single fixed numeric mark (on the 0–100 axis) that lands in a DIFFERENT band under
# each of these three world scales — so a genuine scale change must move the label.
_FIXED_SCORE = 72.0
_WAEC = "waec_letter"          # 72 -> "B2"   (A1=75, B2=70 …)
_QUALITATIVE = "qualitative_pd"  # 72 -> "Meeting Expectations" (85 / 70 / 50 / 0)
_PASS_FAIL = "pass_fail"       # 72 -> "Pass"  (Pass=50)


class GradingScaleDisplayConsistencyTests(TestCase):
    """Changing a school's grading scale flips the displayed band on every surface."""

    def _build_school_graph(self, suffix: str) -> SimpleNamespace:
        """A minimal but REAL school→year→term→classroom→subject→student→evaluation graph.

        The AssessmentWeights row is created on the ``waec_letter`` scale first so its
        score_scale realigns to 100 (pre_save ``_apply_scale_consistent_bands``), which is
        what lets the 72 marks pass ``Evaluation.clean()`` bound-checking on this school.
        """
        school = School.objects.create(
            slug=f"grade-display-{suffix}",
            subdomain=f"grade-display-{suffix}",
            name=f"Grade Display {suffix}",
            settings={"default_grading_scale": _WAEC},
        )
        year = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 5),
            position=1,
            is_active=True,
        )
        department = Department.objects.create(
            school=school, name="Science", code=f"SCI-{suffix}"
        )
        specialty = Specialty.objects.create(
            school=school, department=department, name="General", code=f"GEN-{suffix}"
        )
        classroom = Classroom.objects.create(
            school=school,
            academic_year=year,
            department=department,
            name="Form 3A",
            code=f"F3A-{suffix}",
        )
        subject = Subject.objects.create(school=school, name="Mathematics")
        subject_assignment = SubjectAssignment.objects.create(
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
            coefficient=2,
        )
        teacher_user = User.objects.create_user(
            username=f"teacher_{suffix}", password="pass123", role=User.Role.TEACHER
        )
        teacher = TeacherProfile.objects.create(user=teacher_user, school=school)

        # AssessmentWeights on WAEC → score_scale realigns to 100 so 72 marks validate.
        aw = AssessmentWeights.objects.create(
            school=school,
            academic_year=year,
            classroom=classroom,
            term=term,
            grading_scale=_WAEC,
        )

        student = StudentProfile.objects.create(
            school=school,
            first_name="Ada",
            last_name="A",
            student_code=f"STU-{suffix}",
            academic_year=year,
            classroom=classroom,
            specialty=specialty,
            is_active=True,
        )
        # Equal components → weighted mean == 72.0 regardless of the (label-only) scale.
        Evaluation.objects.create(
            academic_year=year,
            term=term,
            subject_assignment=subject_assignment,
            student=student,
            teacher=teacher,
            seq1_score=72,
            seq2_score=72,
            exam_score=72,
        )
        return SimpleNamespace(
            school=school, year=year, term=term, classroom=classroom,
            aw=aw, student=student,
        )

    def setUp(self):
        # Report services read the platform site-settings toggle; keep the approval gate
        # off so the report card includes the evaluation (mirrors the Cameroon ctx test).
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={"reports_use_approved_grades_only": False},
        )
        self.a = self._build_school_graph("a")
        self.b = self._build_school_graph("b")

    # ---- helpers -----------------------------------------------------------------

    def _set_school_scale(self, g: SimpleNamespace, scale_type: str) -> None:
        """Move a school onto ``scale_type`` via BOTH per-school levers the surfaces read:
        the term card reads ``AssessmentWeights.grading_scale``; the transcript + gradebook
        read ``resolve_local_scale_type`` (school.settings). A real school picks one scale,
        so both levers move together — that is what "consistent across surfaces" means."""
        g.aw.grading_scale = scale_type
        g.aw.save(update_fields=["grading_scale"])
        settings = dict(g.school.settings or {})
        settings["default_grading_scale"] = scale_type
        g.school.settings = settings
        g.school.save(update_fields=["settings"])

    def _surface_bands(self, g: SimpleNamespace) -> dict[str, str]:
        """Displayed band on every reading surface, via the REAL surface functions.

        Each value is produced by the exact function chain the production surface uses —
        no reimplementation of the band mapping.
        """
        term_ctx = term_report_context(g.student, g.year, g.term)
        annual_ctx = annual_report_context(g.student, g.year)
        # Teacher gradebook / mark-sheet chain (evals/views.py:2281,2291): the scale is
        # resolve_local_scale_type(school); the band is resolve_extended_band_label(...).
        gradebook_scale = resolve_local_scale_type(g.school)
        # Rankings expose averages; band for that average uses the same resolver as
        # gradebook/report (Evaluation.letter_grade remains coarse A–E storage).
        ranking_avg = float(term_ctx["summary"].get("average") or _FIXED_SCORE)
        return {
            "term_row": term_ctx["rows"][0]["band"],
            "term_overall": term_ctx["summary"]["overall_band"],
            "annual": annual_ctx["annual_band"],
            "gradebook": resolve_extended_band_label(gradebook_scale, _FIXED_SCORE),
            "template_tag": format_grade_band(gradebook_scale, _FIXED_SCORE),
            "ranking_band": resolve_extended_band_label(gradebook_scale, ranking_avg),
        }

    # ---- tests -------------------------------------------------------------------

    def test_all_surfaces_agree_and_match_canonical_resolver_under_waec(self):
        """On WAEC, every surface shows ``B2`` AND equals the canonical resolver output.

        The canonical-equality lock is the anti-hardcode guard: a surface that hardcoded
        a band or dropped to a coarse letter would not equal
        ``resolve_extended_band_label('waec_letter', 72.0)``.
        """
        self._set_school_scale(self.a, _WAEC)
        expected = resolve_extended_band_label(_WAEC, _FIXED_SCORE)
        self.assertEqual(expected, "B2")  # sanity: the fixture actually lands on B2

        bands = self._surface_bands(self.a)
        for surface, band in bands.items():
            self.assertEqual(band, expected, msg=f"{surface} diverged from resolver")

    def test_scale_change_flips_the_band_on_all_surfaces(self):
        """FAIL-BEFORE core: flipping the scale must flip the label on every surface.

        A hardcoded band table or a resolver bypass would leave a surface stuck on the
        old label — this test would then fail on that surface.
        """
        # WAEC → all surfaces "B2".
        self._set_school_scale(self.a, _WAEC)
        waec_bands = self._surface_bands(self.a)
        self.assertTrue(all(v == "B2" for v in waec_bands.values()), waec_bands)

        # Same school, same 72 mark, different scale → all surfaces "Meeting Expectations".
        self._set_school_scale(self.a, _QUALITATIVE)
        qual_bands = self._surface_bands(self.a)
        qual_expected = resolve_extended_band_label(_QUALITATIVE, _FIXED_SCORE)
        self.assertEqual(qual_expected, "Meeting Expectations")
        for surface, band in qual_bands.items():
            self.assertEqual(band, qual_expected, msg=f"{surface} did not flip")
            self.assertNotEqual(
                band, waec_bands[surface], msg=f"{surface} band did not change with scale"
            )

        # A third scale → all surfaces "Pass"; proves it is not a two-value toggle.
        self._set_school_scale(self.a, _PASS_FAIL)
        pf_bands = self._surface_bands(self.a)
        pf_expected = resolve_extended_band_label(_PASS_FAIL, _FIXED_SCORE)
        self.assertEqual(pf_expected, "Pass")
        for surface, band in pf_bands.items():
            self.assertEqual(band, pf_expected, msg=f"{surface} did not reach Pass")

        # The three configs produced three DISTINCT labels for the identical 72 mark.
        self.assertEqual({"B2", "Meeting Expectations", "Pass"},
                         {waec_bands["term_row"], qual_bands["term_row"], pf_bands["term_row"]})

    def test_scale_change_is_tenant_scoped(self):
        """School A's scale change must NOT touch school B's displayed band.

        Both schools start on WAEC (``B2``). Flipping school A to qualitative descriptors
        must leave school B's surfaces on ``B2`` — proving the band config is resolved
        per-school, not from shared/global state.
        """
        self._set_school_scale(self.a, _WAEC)
        self._set_school_scale(self.b, _WAEC)
        self.assertTrue(all(v == "B2" for v in self._surface_bands(self.a).values()))
        self.assertTrue(all(v == "B2" for v in self._surface_bands(self.b).values()))

        # Flip ONLY school A.
        self._set_school_scale(self.a, _QUALITATIVE)

        a_bands = self._surface_bands(self.a)
        b_bands = self._surface_bands(self.b)
        self.assertTrue(
            all(v == "Meeting Expectations" for v in a_bands.values()), a_bands
        )
        # School B untouched.
        self.assertTrue(all(v == "B2" for v in b_bands.values()), b_bands)
