"""A classroom could not be CREATED across the sync boundary in either direction.

Found by running the insert, 2026-08-20, while proving delete propagation.

``classroom`` is one of the three ORIGINAL synced entities and keeps a curated field set.
That set was ``{"name", "academic_year_id"}`` — but ``Classroom.department`` is NOT NULL
and ``Classroom.code`` is a required UNIQUE column, neither of which was on it. So:

  * a class created on the CLOUD in September reached the appliance's create path and
    died on ``NOT NULL constraint failed: academics_classroom.department_id`` — reported
    as a per-row 422 and otherwise invisible. The class simply did not exist offline;
  * a class created OFFLINE could never be pushed up, for the same reason;
  * and had ``department_id`` alone been added, the SECOND created classroom would have
    collided on ``code=""`` — unique — so both columns are required for this to work at
    all.

Only UPDATES worked, which is exactly why it went unnoticed: the pk-preserving clone
already had every classroom that existed at clone time, and edits to those converged
perfectly. Everything created afterwards did not.

The exam/term governance booleans (``gce_eligible``, ``allows_third_term``) are
deliberately still OFF the rail: they decide who may be registered for a certification
exam, which is the same class of cloud-governed switch as
``academic_year.enable_gce_registration``, already excluded for that reason.
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department
from apps.accounts.models import User
from apps.api.sync_services import _get_entity_config, apply_changes, apply_edge_inserts
from apps.schools.models import School


class ClassroomCreatesAcrossTheRailTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Room School", slug="room-school", subdomain="room-school"
        )
        self.admin = User.objects.create_user(
            username="room-admin", password="x" * 12, role=User.Role.ADMIN, is_staff=True
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027-room",
            start_date=date(2026, 9, 1), end_date=date(2027, 6, 30),
        )
        self.dept = Department.objects.create(school=self.school, name="Sci", code="SCI-R")

    def test_the_required_columns_are_on_the_rail(self):
        """The seal. Dropping either one silently reinstates the bug: creates start
        failing again as a per-row 422 that nothing surfaces as a missing class."""
        _model, allowed = _get_entity_config(include_derived=True)["classroom"]
        self.assertIn("department_id", allowed)
        self.assertIn("code", allowed)

    def test_a_class_created_on_the_cloud_reaches_the_box(self):
        new_pk = (Classroom.objects.order_by("-pk").values_list("pk", flat=True).first() or 0) + 500
        out = apply_changes(
            str(self.school.id), self.admin,
            [{
                "entity_type": "classroom", "id": new_pk, "client_offline_id": "",
                "changes": {
                    "name": "Form 1A", "academic_year_id": self.year.pk,
                    "department_id": self.dept.pk, "code": "F1A-CLOUD",
                },
                "updated_at": "2026-09-01T08:00:00+00:00",
            }],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        self.assertEqual(out["results"][0]["status"], 201, out["results"])
        room = Classroom.objects.get(pk=new_pk)
        self.assertEqual((room.name, room.code), ("Form 1A", "F1A-CLOUD"))
        self.assertEqual(room.department_id, self.dept.pk)

    def test_a_class_created_offline_can_be_pushed_up(self):
        out = apply_edge_inserts(
            str(self.school.id), self.admin,
            [{
                "entity_type": "classroom", "id": 4242, "client_offline_id": "room-anchor-1",
                "changes": {
                    "name": "Form 2B", "academic_year_id": self.year.pk,
                    "department_id": self.dept.pk, "code": "F2B-EDGE",
                },
                "updated_at": "2026-09-01T08:00:00+00:00",
            }],
            sync_origin="edge-push",
        )
        self.assertEqual(out["created"], 1, out["results"])
        room = Classroom.objects.get(client_offline_id="room-anchor-1")
        self.assertEqual(room.code, "F2B-EDGE")
        self.assertEqual(room.school_id, self.school.id)

    def test_two_offline_classes_do_not_collide_on_an_empty_code(self):
        """Adding department_id WITHOUT code would have moved the failure rather than
        fixed it: `code` is unique, so the second create would die on `code=""`."""
        rows = [
            {
                "entity_type": "classroom", "id": 5001, "client_offline_id": "anchor-a",
                "changes": {
                    "name": "A", "academic_year_id": self.year.pk,
                    "department_id": self.dept.pk, "code": "CODE-A",
                },
                "updated_at": "2026-09-01T08:00:00+00:00",
            },
            {
                "entity_type": "classroom", "id": 5002, "client_offline_id": "anchor-b",
                "changes": {
                    "name": "B", "academic_year_id": self.year.pk,
                    "department_id": self.dept.pk, "code": "CODE-B",
                },
                "updated_at": "2026-09-01T08:00:00+00:00",
            },
        ]
        out = apply_edge_inserts(str(self.school.id), self.admin, rows, sync_origin="edge-push")
        self.assertEqual(out["created"], 2, out["results"])

    def test_a_duplicate_business_code_is_reported_not_corrupted(self):
        """Non-negotiable #2 of the upgrade brief: a natural-key collision on a
        human-meaningful identifier is a conflict for a human, never something to dodge by
        appending a node id."""
        Classroom.objects.create(
            school=self.school, academic_year=self.year, department=self.dept,
            name="Existing", code="TAKEN-CODE",
        )
        out = apply_edge_inserts(
            str(self.school.id), self.admin,
            [{
                "entity_type": "classroom", "id": 6001, "client_offline_id": "anchor-dup",
                "changes": {
                    "name": "Dup", "academic_year_id": self.year.pk,
                    "department_id": self.dept.pk, "code": "TAKEN-CODE",
                },
                "updated_at": "2026-09-01T08:00:00+00:00",
            }],
            sync_origin="edge-push",
        )
        self.assertEqual(out["results"][0]["status"], 422)
        self.assertEqual(out["results"][0]["data"]["error"], "insert_failed")
        self.assertEqual(Classroom.objects.filter(code="TAKEN-CODE").count(), 1)

    def test_the_exam_governance_switches_stay_off_the_rail(self):
        _model, allowed = _get_entity_config(include_derived=True)["classroom"]
        self.assertNotIn("gce_eligible", allowed)
        self.assertNotIn("allows_third_term", allowed)
