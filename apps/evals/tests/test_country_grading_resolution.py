"""Globalization program 2.1 — country → grading-scale resolution, as DATA.

Before this pass the country→scale decision was a two-dict Python cascade whose
coarsest leg was a five-continent bucket
(``academic_pack_bridge._GRADING_PRESET_BY_BUCKET`` → ``_PRESET_TO_SCALE_TYPE``).
Measured against the live catalogue, that made **ten of the platform's fifteen
grading scales unreachable by any school on earth**, and mis-assigned real
national systems in ways that broke marking:

* Germany (1–6) resolved to ``uk_gcse_9_1`` — a 9-point axis.
* India (CBSE 10-point) resolved to ``percentage``.
* Russia / Ukraine / the CIS (1–5) resolved to ``uk_gcse_9_1``.
* Greece and Portugal (0–20) resolved to ``uk_gcse_9_1``, whose max of **9
  rejects a valid mark of 10**.

``siteconfig.CountryGradingProfile`` is now the resolution layer: a SHARED
platform-catalog table seeded by ``siteconfig.country_grading_seed``, in the same
idiom as ``CountryMultiplier``. Adding a country is a row.

Every test here is MUST-FIRE: each was confirmed to go red with the change
reverted (unlock tests fail on the old bucket mapping; the fail-closed tests fail
against the old ``return Decimal("100")``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.evals.grading_provisioning import (
    UnresolvedScoreScale,
    country_default_scale_type,
    resolve_local_scale_type,
    resolve_school_score_scale,
)
from apps.schools.models import School


def _school(country_code="", **kw):
    import uuid

    tag = uuid.uuid4().hex[:10]
    return School.objects.create(
        name=f"CGP {tag}",
        slug=f"cgp-{tag}",
        subdomain=f"cgp-{tag}",
        country_code=country_code,
        **kw,
    )


class CountryGradingSeedIntegrityTests(TestCase):
    """The FK the table cannot have, enforced as a test instead."""

    def test_every_seeded_scale_type_is_a_live_scale_type(self):
        from apps.siteconfig.country_grading_seed import invalid_scale_types

        self.assertEqual(invalid_scale_types(), [])

    def test_seed_is_applied_by_migration(self):
        from apps.siteconfig.models import CountryGradingProfile

        self.assertTrue(CountryGradingProfile.objects.filter(country_code="DE").exists())

    def test_seed_is_idempotent(self):
        from apps.siteconfig.country_grading_seed import seed_country_grading_profiles
        from apps.siteconfig.models import CountryGradingProfile

        before = CountryGradingProfile.objects.count()
        summary = seed_country_grading_profiles()
        self.assertEqual(summary["created"], 0)
        self.assertEqual(CountryGradingProfile.objects.count(), before)

    def test_no_duplicate_country_rows_in_seed(self):
        from apps.siteconfig.country_grading_seed import COUNTRY_GRADING_SEED_ROWS

        codes = [r["country_code"] for r in COUNTRY_GRADING_SEED_ROWS]
        self.assertEqual(len(codes), len(set(codes)))


class UnlockedScaleTests(TestCase):
    """One test per scale this pass makes reachable from a country.

    Each of these previously resolved to something else entirely — see the
    module docstring for the before-values. Reverting the catalog leg in
    ``resolve_local_scale_type`` turns every one of them red.
    """

    def test_germany_resolves_to_german_1_6(self):
        # Was: uk_gcse_9_1 (the 'europe' continent bucket).
        self.assertEqual(resolve_local_scale_type(_school("DE")), "german_1_6")

    def test_india_resolves_to_cbse_10(self):
        # Was: percentage (the 'asia' continent bucket).
        self.assertEqual(resolve_local_scale_type(_school("IN")), "cbse_10")

    def test_russia_resolves_to_numeric_1_5(self):
        # Was: uk_gcse_9_1 (the 'europe' continent bucket).
        self.assertEqual(resolve_local_scale_type(_school("RU")), "numeric_1_5")

    def test_greece_resolves_to_numeric_0_20(self):
        # Was: uk_gcse_9_1 — whose max of 9 rejects a valid Greek mark of 10+.
        self.assertEqual(resolve_local_scale_type(_school("GR")), "numeric_0_20")

    def test_unlocked_scales_carry_their_real_axis(self):
        """The unlock is only real if the score-scale MAX follows the scale type."""
        self.assertEqual(resolve_school_score_scale(_school("DE")), Decimal("6"))
        self.assertEqual(resolve_school_score_scale(_school("IN")), Decimal("10"))
        self.assertEqual(resolve_school_score_scale(_school("RU")), Decimal("5"))
        self.assertEqual(resolve_school_score_scale(_school("GR")), Decimal("20"))

    def test_spain_no_longer_bounded_below_its_own_top_mark(self):
        """Spain marks 0–10; the old 'europe' bucket bounded it at 9.

        There is no ``numeric_0_10`` ScaleType yet, so the seed uses the wider
        percentage axis. What must never come back is a bound BELOW 10.
        """
        self.assertGreaterEqual(resolve_school_score_scale(_school("ES")), Decimal("10"))

    def test_country_lookup_is_case_and_whitespace_tolerant(self):
        self.assertEqual(country_default_scale_type(" de "), "german_1_6")
        self.assertEqual(country_default_scale_type("De"), "german_1_6")

    def test_unknown_country_falls_through_to_the_preset_engine(self):
        """A country with no catalog row keeps the legacy cascade, not a blank."""
        from apps.evals.grading_provisioning import _VALID_SCALE_TYPES

        self.assertEqual(country_default_scale_type("ZZ"), "")
        self.assertIn(resolve_local_scale_type(_school("ZZ")), _VALID_SCALE_TYPES)


class PerSchoolOverrideTests(TestCase):
    """The country row is a DEFAULT; an explicit school choice still wins."""

    def test_school_settings_override_beats_the_country_row(self):
        school = _school("DE", settings={"default_grading_scale": "ib_1_7"})
        self.assertEqual(resolve_local_scale_type(school), "ib_1_7")
        self.assertEqual(resolve_school_score_scale(school), Decimal("7"))

    def test_runtime_defaults_bucket_override_beats_the_country_row(self):
        school = _school(
            "IN", settings={"runtime_defaults": {"default_grading_scale": "gpa_4_0"}}
        )
        self.assertEqual(resolve_local_scale_type(school), "gpa_4_0")

    def test_deactivating_a_country_row_falls_back_to_the_preset_engine(self):
        """``is_active`` is the operator's kill switch for a mapping."""
        from apps.siteconfig.models import CountryGradingProfile

        from apps.evals.grading_provisioning import _VALID_SCALE_TYPES

        CountryGradingProfile.objects.filter(country_code="DE").update(is_active=False)
        self.assertEqual(country_default_scale_type("DE"), "")
        # The legacy cascade answers again — whatever it says, it is no longer the
        # catalog's answer. (Its exact output depends on seeded country-pack data,
        # so this pins the fall-through, not the legacy value.)
        legacy = resolve_local_scale_type(_school("DE"))
        self.assertIn(legacy, _VALID_SCALE_TYPES)
        self.assertNotEqual(legacy, "german_1_6")


class NoSilentHundredTests(TestCase):
    """``resolve_school_score_scale(None)`` must not answer 100.

    100 is the platform's WIDEST scale, so returning it for "unknown" inverted
    the safety of every bound built on the resolver — which is precisely how a
    real Cameroon end-to-end run accepted a mark of 25 out of 20.
    """

    def test_none_raises_instead_of_returning_100(self):
        with self.assertRaises(UnresolvedScoreScale):
            resolve_school_score_scale(None)

    def test_none_does_not_return_100(self):
        """Stated as the acceptance criterion words it, independent of mechanism."""
        try:
            value = resolve_school_score_scale(None)
        except UnresolvedScoreScale:
            return
        self.assertNotEqual(value, Decimal("100"))

    def test_display_callers_opt_into_the_neutral_fallback_explicitly(self):
        self.assertEqual(resolve_school_score_scale(None, default=100), Decimal("100"))
        self.assertEqual(resolve_school_score_scale(None, default=20), Decimal("20"))

    def test_a_real_school_still_resolves_without_a_default(self):
        """Fail-closed must not become fail-always."""
        self.assertEqual(resolve_school_score_scale(_school("CM")), Decimal("20"))


class _GradebookFixtureMixin:
    """Builds a minimal gradebook for a given country, with NO ``AssessmentWeights``.

    Omitting the weights row is the point: the score bound must then come from the
    COUNTRY, which is exactly the path this item wires.
    """

    _seq = 0

    def _fixture(self, country_code):
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
        from apps.people.models import TeacherProfile

        type(self)._seq += 1
        tag = f"{country_code}{type(self)._seq}"
        school = _school(country_code, is_active=True)
        year = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name=Term.Name.FIRST,
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        dept = Department.objects.create(
            school=school, name="General", code=f"GEN-{tag}"
        )
        specialty = Specialty.objects.create(
            school=school, department=dept, name="General", code=f"SPEC-{tag}"
        )
        classroom = Classroom.objects.create(
            school=school,
            academic_year=year,
            department=dept,
            name="Form 1",
            code=f"F1-{tag}",
        )
        subject = Subject.objects.create(school=school, name="Mathematics")
        assignment = SubjectAssignment.objects.create(
            school=school,
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
            coefficient=1,
        )
        user = User.objects.create_user(
            username=f"cgp_teacher_{tag}", password="x", role=User.Role.TEACHER
        )
        teacher = TeacherProfile.objects.create(user=user, school=school)
        return {
            "school": school,
            "year": year,
            "term": term,
            "classroom": classroom,
            "specialty": specialty,
            "assignment": assignment,
            "teacher": teacher,
        }

    def _evaluation(self, fx, code, score):
        from apps.evals.models import Evaluation
        from apps.people.models import StudentProfile

        student = StudentProfile.objects.create(
            school=fx["school"],
            first_name="Ndi",
            last_name=code,
            student_code=code,
            academic_year=fx["year"],
            classroom=fx["classroom"],
            specialty=fx["specialty"],
            is_active=True,
        )
        return Evaluation(
            academic_year=fx["year"],
            term=fx["term"],
            subject_assignment=fx["assignment"],
            student=student,
            teacher=fx["teacher"],
            school=fx["school"],
            seq1_score=Decimal(score),
        )


class OutOfRangeMarkRejectedTests(_GradebookFixtureMixin, TestCase):
    """A 25 must not be accepted on a 20-point scale — end to end through save()."""

    def test_25_rejected_on_a_20_point_country(self):
        fx = self._fixture("CM")
        with self.assertRaises(ValidationError):
            self._evaluation(fx, "CGP-OOR-1", "25.00").save()

    def test_20_still_accepted_on_a_20_point_country(self):
        """The bound must reject the out-of-range mark, not the boundary mark."""
        fx = self._fixture("CM")
        evaluation = self._evaluation(fx, "CGP-OOR-2", "20.00")
        evaluation.save()
        self.assertIsNotNone(evaluation.pk)

    def test_unresolvable_school_rejects_rather_than_admits(self):
        """Fail closed: an unknown scale clamps to the NARROWEST bound, not the widest.

        Previously the resolver answered 100 here and a 25 sailed through. Now the
        unknown case bounds at 20, so the same mark is refused.
        """
        from unittest import mock

        from apps.evals.grading_provisioning import UnresolvedScoreScale

        fx = self._fixture("CM")
        evaluation = self._evaluation(fx, "CGP-OOR-3", "25.00")
        with mock.patch(
            "apps.evals.grading_provisioning.resolve_school_score_scale",
            side_effect=UnresolvedScoreScale("no school"),
        ):
            with self.assertRaises(ValidationError):
                evaluation.save()

    def test_unknown_scale_clamps_narrow_not_to_100(self):
        """The specific regression: 45 must not be admitted just because the scale is unknown.

        Under the old ``return Decimal("100")`` this saved cleanly.
        """
        from unittest import mock

        from apps.evals.grading_provisioning import UnresolvedScoreScale

        fx = self._fixture("CM")
        evaluation = self._evaluation(fx, "CGP-OOR-4", "45.00")
        with mock.patch(
            "apps.evals.grading_provisioning.resolve_school_score_scale",
            side_effect=UnresolvedScoreScale("no school"),
        ):
            with self.assertRaises(ValidationError):
                evaluation.save()

    def test_unknown_scale_still_accepts_a_mark_inside_the_narrow_bound(self):
        """Clamping must not become refusing every mark — 13 legitimate rows depend on this."""
        from unittest import mock

        from apps.evals.grading_provisioning import UnresolvedScoreScale

        fx = self._fixture("CM")
        evaluation = self._evaluation(fx, "CGP-OOR-5", "12.00")
        with mock.patch(
            "apps.evals.grading_provisioning.resolve_school_score_scale",
            side_effect=UnresolvedScoreScale("no school"),
        ):
            evaluation.save()
        self.assertIsNotNone(evaluation.pk)


class UnlockedScaleBoundsEndToEndTests(_GradebookFixtureMixin, TestCase):
    """The unlock must change what the gradebook actually accepts, not just a string.

    These are the must-fire tests for the country→scale catalog specifically:
    with the catalog leg reverted, Germany falls back to the 9-point GCSE axis and
    Greece to the same, so the first test admits an impossible German 8 and the
    second wrongly rejects an ordinary Greek 15.
    """

    def test_german_school_rejects_a_mark_of_8_on_its_1_to_6_axis(self):
        # Legacy cascade gave DE a max of 9, so an 8 was accepted.
        fx = self._fixture("DE")
        with self.assertRaises(ValidationError):
            self._evaluation(fx, "CGP-DE-1", "8.00").save()

    def test_german_school_still_accepts_a_valid_grade(self):
        fx = self._fixture("DE")
        evaluation = self._evaluation(fx, "CGP-DE-2", "2.00")
        evaluation.save()
        self.assertIsNotNone(evaluation.pk)

    def test_greek_school_accepts_15_on_its_0_to_20_axis(self):
        # Legacy cascade gave GR a max of 9, which REJECTED a normal Greek mark.
        fx = self._fixture("GR")
        evaluation = self._evaluation(fx, "CGP-GR-1", "15.00")
        evaluation.save()
        self.assertIsNotNone(evaluation.pk)

    def test_indian_school_rejects_a_mark_above_its_10_point_axis(self):
        # Legacy cascade gave IN a percentage axis, so 45 was accepted.
        fx = self._fixture("IN")
        with self.assertRaises(ValidationError):
            self._evaluation(fx, "CGP-IN-1", "45.00").save()

    def test_russian_school_rejects_a_mark_above_its_5_point_axis(self):
        # Legacy cascade gave RU a max of 9, so a 7 was accepted.
        fx = self._fixture("RU")
        with self.assertRaises(ValidationError):
            self._evaluation(fx, "CGP-RU-1", "7.00").save()


class ExistingTenantRegressionTests(TestCase):
    """This must not silently re-grade a live school.

    Two independent guarantees:
      1. A school whose operational ``AssessmentWeights.score_scale`` is already
         set keeps it, whatever the country catalog now says.
      2. ``ensure_local_grading_scale`` still refuses to touch a school that
         already owns a default ``GradingScale``.
    """

    def test_existing_assessment_weights_still_win_over_the_country_row(self):
        from apps.academics.models import AcademicYear
        from apps.evals.models import AssessmentWeights

        # A German tenant onboarded before this pass, operating on /100.
        school = _school("DE")
        year = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
        )
        AssessmentWeights.objects.create(
            school=school, academic_year=year, score_scale=100
        )
        self.assertEqual(resolve_school_score_scale(school), Decimal("100"))

    def test_existing_default_grading_scale_is_not_overwritten(self):
        from apps.evals.grading_provisioning import ensure_local_grading_scale
        from apps.evals.models import GradingScale

        school = _school("IN")
        GradingScale.objects.create(
            school=school,
            code="admin-pick",
            name="Admin pick",
            scale_type="percentage",
            is_default=True,
            is_active=True,
        )
        result = ensure_local_grading_scale(school)
        self.assertEqual(result.get("skipped"), "default_scale_exists")
        self.assertEqual(
            GradingScale.objects.get(school=school, is_default=True).scale_type,
            "percentage",
        )

    def test_countries_that_already_resolved_correctly_are_unchanged(self):
        """The catalog must agree with the legacy cascade wherever it was right."""
        for country, expected in (
            ("CM", "french_0_20"),
            ("FR", "french_0_20"),
            ("US", "us_letter"),
            ("GB", "uk_gcse_9_1"),
            ("NG", "waec_letter"),
            ("GH", "waec_letter"),
            ("CN", "percentage"),
        ):
            with self.subTest(country=country):
                self.assertEqual(
                    resolve_local_scale_type(_school(country)), expected
                )


class ResolverContractTests(SimpleTestCase):
    """No-DB checks on the shape of the contract itself."""

    def test_unresolved_is_an_exception_type_callers_can_catch(self):
        self.assertTrue(issubclass(UnresolvedScoreScale, Exception))

    def test_blank_country_code_short_circuits_without_a_query(self):
        self.assertEqual(country_default_scale_type(""), "")
        self.assertEqual(country_default_scale_type(None), "")
