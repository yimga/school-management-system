"""Per-field direction policy leaked on the INSERT path.

``_DOWN_ONLY_FIELDS_PER_ENTITY`` declares fields the cloud owns: the box may READ them
but a box-authored value must never be applied upward. That was enforced in
``_apply_changes_inner`` (the UPDATE path) and **nowhere else**. ``apply_edge_inserts``
— the offline-CREATED row path — filtered candidate fields only by the entity's allowed
set and the model's settable names, so a row carrying ``client_offline_id`` could ship a
down-only field UP and have it written on the cloud.

That makes the policy trivially bypassable: the same value the update path refuses with
409 lands cleanly if the box presents it as a new row instead of an edit. Direction is a
property of the FIELD, so it has to hold on every inbound path.

Proven here against the already-registered ``subject_assignment.coefficient`` (the seed
entry) so the hole is demonstrated independently of any newly registered entity.
"""
from __future__ import annotations

import datetime as dt

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    SubjectAssignment,
)
from apps.accounts.models import User
from apps.api.sync_services import _DOWN_ONLY_FIELDS_PER_ENTITY, apply_edge_inserts
from apps.people.models import TeacherProfile
from apps.schools.models import School


class _Fixture(TestCase):
    """The known-good SubjectAssignment graph (mirrors evals' own test fixture)."""

    def setUp(self):
        self.school = School.objects.create(
            name="Direction School", slug="direction-school", subdomain="direction-school"
        )
        self.admin = User.objects.create_user(
            username="direction-admin", password="x" * 10, role=User.Role.ADMIN, is_staff=True
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026",
            start_date=dt.date(2026, 9, 1),
            end_date=dt.date(2027, 6, 30),
        )
        self.dept = Department.objects.create(school=self.school, name="Science", code="SCI")
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Form 4",
            code="F4-DIR",
        )
        teacher_user = User.objects.create_user(
            username="direction-teacher", password="x" * 10, role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            school=self.school, user=teacher_user, staff_id="T-DIR-1"
        )
        from apps.academics.models import Specialty, Subject, Term

        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            start_date=dt.date(2026, 9, 1),
            end_date=dt.date(2026, 12, 15),
        )
        self.specialty = Specialty.objects.create(
            school=self.school, department=self.dept, name="Pure Science", code="PS-DIR"
        )
        self.subject = Subject.objects.create(
            school=self.school, name="Physics", code="PHY-DIR"
        )


class DownOnlyFieldsAreRefusedOnInsertTests(_Fixture):
    def test_the_seed_entry_is_still_declared(self):
        """Guards the premise: this test is meaningless if the policy map moved."""
        self.assertIn("coefficient", _DOWN_ONLY_FIELDS_PER_ENTITY.get("subject_assignment", set()))

    def _insert_row(self, coefficient):
        return [
            {
                "entity_type": "subject_assignment",
                "id": 987654,  # a box-local pk, meaningless on the cloud
                "client_offline_id": "offline-sa-direction-1",
                "changes": {
                    "subject_id": self.subject.pk,
                    "classroom_id": self.classroom.pk,
                    "specialty_id": self.specialty.pk,
                    "term_id": self.term.pk,
                    "academic_year_id": self.year.pk,
                    "coefficient": coefficient,
                },
                "updated_at": None,
            }
        ]

    def test_box_authored_insert_cannot_set_a_down_only_field(self):
        out = apply_edge_inserts(
            str(self.school.id), self.admin, self._insert_row("9.00"), sync_origin="edge-push"
        )
        created = SubjectAssignment.objects.filter(
            school=self.school, client_offline_id="offline-sa-direction-1"
        ).first()
        self.assertIsNotNone(created, out)
        self.assertNotEqual(
            str(created.coefficient),
            "9.00",
            "a box-authored INSERT wrote a down-only field the UPDATE path refuses — "
            "the direction policy is bypassable by presenting an edit as a new row",
        )

    def test_the_rejection_is_reported_not_silent(self):
        out = apply_edge_inserts(
            str(self.school.id), self.admin, self._insert_row("9.00"), sync_origin="edge-push"
        )
        payloads = [str(r.get("data")) for r in out["results"]]
        self.assertTrue(
            any("down_only" in p for p in payloads),
            f"the dropped field was not surfaced to the caller: {payloads}",
        )

    def test_the_rest_of_the_row_still_lands(self):
        """A refused field must cost only that field, never the whole record."""
        apply_edge_inserts(
            str(self.school.id), self.admin, self._insert_row("9.00"), sync_origin="edge-push"
        )
        created = SubjectAssignment.objects.filter(
            school=self.school, client_offline_id="offline-sa-direction-1"
        ).first()
        self.assertIsNotNone(created)
        self.assertEqual(created.subject_id, self.subject.pk)
        self.assertEqual(created.specialty_id, self.specialty.pk)

    def test_a_cloud_pull_insert_may_set_the_field(self):
        """Direction, not exclusion: inbound from the cloud the value is authoritative."""
        apply_edge_inserts(
            str(self.school.id), self.admin, self._insert_row("7.00"), sync_origin="cloud-pull"
        )
        created = SubjectAssignment.objects.filter(
            school=self.school, client_offline_id="offline-sa-direction-1"
        ).first()
        self.assertIsNotNone(created)
        self.assertEqual(str(created.coefficient), "7.00")
