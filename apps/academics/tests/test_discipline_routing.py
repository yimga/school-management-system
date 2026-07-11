"""Discipline points ledger + incident routing (metric 11)."""

import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.discipline_services import student_behavior_point_total
from apps.academics.models import Incident
from apps.academics.models_discipline import BehaviorPointLedger, RestorativeAction
from apps.people.models import StudentProfile
from apps.schools.models import School

User = get_user_model()


class DisciplineRoutingTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Disc School",
            slug=f"disc-{uuid.uuid4().hex[:10]}",
            subdomain=f"disc-{uuid.uuid4().hex[:10]}",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Sam",
            last_name="Student",
            student_code=f"ST-{uuid.uuid4().hex[:6]}",
        )
        self.staff = User.objects.create_user(
            username=f"staff-{uuid.uuid4().hex[:8]}",
            email="s@disc.test",
            password="x",
            role=User.Role.TEACHER,
        )

    def test_medium_incident_accrues_points_and_restorative(self):
        incident = Incident.objects.create(
            school=self.school,
            student=self.student,
            incident_type=Incident.Type.BEHAVIOR,
            severity=Incident.Severity.MEDIUM,
            date=date.today(),
            description="Disruption",
            notify_parent=False,
        )
        self.assertEqual(
            BehaviorPointLedger.objects.filter(school=self.school, student=self.student).count(),
            1,
        )
        self.assertTrue(
            RestorativeAction.objects.filter(school=self.school, incident=incident).exists()
        )

    def test_escalation_when_threshold_exceeded(self):
        for _ in range(2):
            Incident.objects.create(
                school=self.school,
                student=self.student,
                incident_type=Incident.Type.BEHAVIOR,
                severity=Incident.Severity.HIGH,
                date=date.today(),
                notify_parent=False,
            )
        total = student_behavior_point_total(school=self.school, student=self.student)
        self.assertGreaterEqual(total, 10)
        last = Incident.objects.filter(student=self.student).order_by("-id").first()
        self.assertEqual(last.status, Incident.Status.REFERRED)

    def test_signal_notifies_guardian_and_stamps_parent_notified_at(self):
        # Non-API incident creation (admin/bulk/other code) must notify guardians
        # AND stamp parent_notified_at, so the counselor caseload's "flagged but
        # not yet notified" tally is not permanently wrong.
        from apps.finance.models import Notification
        from apps.people.models import StudentGuardian

        parent = User.objects.create_user(
            username=f"par-{uuid.uuid4().hex[:8]}",
            email="p@disc.test",
            password="x",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=parent, student=self.student, relationship="Parent",
        )
        incident = Incident.objects.create(
            school=self.school,
            student=self.student,
            incident_type=Incident.Type.BEHAVIOR,
            severity=Incident.Severity.LOW,
            date=date.today(),
            description="Called out",
            notify_parent=True,
        )
        self.assertTrue(Notification.objects.filter(recipient=parent).exists())
        incident.refresh_from_db()
        self.assertIsNotNone(incident.parent_notified_at)

    def test_notify_parent_false_leaves_timestamp_null(self):
        incident = Incident.objects.create(
            school=self.school,
            student=self.student,
            incident_type=Incident.Type.BEHAVIOR,
            severity=Incident.Severity.LOW,
            date=date.today(),
            notify_parent=False,
        )
        incident.refresh_from_db()
        self.assertIsNone(incident.parent_notified_at)
