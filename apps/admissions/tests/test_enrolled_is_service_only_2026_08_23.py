"""ENROLLED is a CONSEQUENCE of enrolling, never a stage button.

``_ALLOWED_TRANSITIONS[ACCEPTED]`` listed ``ENROLLED``, and
``apps.people.views_backend._applicant_available_transitions`` renders one POST
button for every target ``can_transition`` accepts. So an operator could move an
accepted applicant straight to ENROLLED from the detail page -- and
``backend_applicant_advance_stage`` only writes ``stage``: no StudentProfile is
created, ``enroll_applicant_to_student`` is never reached.

The applicant is then stranded with no in-product way back:

* ``_ALLOWED_TRANSITIONS[ENROLLED]`` is empty, so every stage button disappears;
* ``can_enroll`` answers ``applicant_must_be_accepted_not_ENROLLED``, so the
  Enroll action refuses;
* ``queue_depth._QUEUE_STAGES`` excludes ENROLLED, so the applicant vanishes from
  the admissions cockpit tile.

The child counts as enrolled in the funnel and exists in no roster, gradebook,
attendance register or fee ledger.

The stage is still reachable -- ``enroll_applicant_to_student`` passes
``via_enrollment_service=True`` -- which is the point: the ONLY door into
ENROLLED is the one that also creates the student.
"""

from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase, TestCase

from apps.admissions.application_kernel import (
    ACCEPTED,
    APPLIED,
    ENROLLED,
    LEAD,
    REJECTED,
    UNDER_REVIEW,
    InvalidStageTransition,
    advance_stage,
    attach_document_reference,
    can_enroll,
    can_transition,
    enroll_applicant_to_student,
    list_required_documents,
)


class EnrolledIsNotAStageButtonTests(SimpleTestCase):
    def test_accepted_cannot_walk_itself_to_enrolled(self):
        self.assertFalse(
            can_transition(ACCEPTED, ENROLLED),
            "the stage buttons are built from can_transition; offering ENROLLED "
            "there enrolls a child with no StudentProfile",
        )

    def test_advance_stage_refuses_and_names_the_right_action(self):
        with self.assertRaises(InvalidStageTransition) as ctx:
            advance_stage(
                current_stage=ACCEPTED,
                target_stage=ENROLLED,
                extra_data={},
                actor_id=7,
            )
        self.assertIn("enrol", str(ctx.exception).lower())

    def test_the_other_accepted_transition_is_untouched(self):
        self.assertTrue(can_transition(ACCEPTED, UNDER_REVIEW))

    def test_the_ui_helper_no_longer_offers_it(self):
        """The exact list the applicant detail template renders POST forms from."""
        from apps.people.views_backend import _applicant_available_transitions

        codes = {row["code"] for row in _applicant_available_transitions(ACCEPTED)}
        self.assertNotIn(ENROLLED, codes)
        self.assertIn(UNDER_REVIEW, codes)

    def test_every_other_edge_of_the_fsm_is_unchanged(self):
        self.assertTrue(can_transition(LEAD, APPLIED))
        self.assertTrue(can_transition(APPLIED, UNDER_REVIEW))
        self.assertTrue(can_transition(APPLIED, REJECTED))
        self.assertTrue(can_transition(UNDER_REVIEW, ACCEPTED))
        self.assertTrue(can_transition(REJECTED, UNDER_REVIEW))
        for stage in (LEAD, APPLIED, UNDER_REVIEW, ACCEPTED, REJECTED):
            self.assertFalse(can_transition(ENROLLED, stage))


class TheEnrollmentServiceStillGetsThroughTests(TestCase):
    """Closing the door must not lock out the one caller that is allowed in."""

    def test_enroll_applicant_to_student_still_reaches_enrolled(self):
        from apps.academics.models import AcademicYear, Classroom, Department
        from apps.people.models import Applicant, StudentProfile
        from apps.schools.models import School

        school = School.objects.create(
            name="Adm Gate", slug="adm-gate", subdomain="adm-gate",
            is_active=True, is_approved=True, country_code="US", timezone="UTC",
        )
        ay = AcademicYear.objects.create(
            school=school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 6, 30), is_active=True,
        )
        dept = Department.objects.create(school=school, code="adm-gate-GEN", name="General")
        classroom = Classroom.objects.create(
            school=school, academic_year=ay, department=dept,
            name="Form 1A", code="adm-gate-C1",
        )
        extra = {}
        for spec in list_required_documents():
            extra = attach_document_reference(
                extra_data=extra, document_key=spec.key,
                storage_ref=f"s3://x/{spec.key}.pdf",
            )
        applicant = Applicant.objects.create(
            school=school, first_name="Ada", last_name="Byron",
            email="ada@gate.test", stage=ACCEPTED, extra_data=extra,
        )
        ok, blockers = can_enroll(current_stage=ACCEPTED, extra_data=extra)
        self.assertTrue(ok, blockers)

        result = enroll_applicant_to_student(
            applicant_id=applicant.id, school_id=school.id,
            actor_user_id=None, classroom_id=classroom.id,
        )
        self.assertTrue(result.ok, msg=f"{result.error} {result.blockers}")
        applicant.refresh_from_db()
        self.assertEqual(applicant.stage, ENROLLED)
        # ...and the student the stage claims exists actually does.
        self.assertTrue(
            StudentProfile.objects.filter(id=result.student_id, school=school).exists()
        )
