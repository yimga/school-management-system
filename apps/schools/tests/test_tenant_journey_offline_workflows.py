"""Offline workflow handler tests for tenant journey (Pillar E)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.academics.models import Incident
from apps.people.models import StudentProfile
from apps.schools.launch_playbook import build_launch_playbook
from apps.schools.models import School
from apps.schools.offline_workflow_handlers import apply_tenant_journey_workflow
from apps.setup_studio.models import SetupProgress

User = get_user_model()


class TenantJourneyOfflineWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Offline Journey",
            slug="offline-journey-wf",
            subdomain="offline-journey-wf",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="offline-journey-admin",
            password="Test1234!",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="offline-journey-teacher",
            password="Test1234!",
            role=User.Role.TEACHER,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Test",
            last_name="Student",
        )
        SetupProgress.objects.create(school=self.school, launched_at=timezone.now())

    def test_launch_playbook_ack_persists(self):
        result = apply_tenant_journey_workflow(
            self.school.pk,
            self.admin.pk,
            "launch_playbook_ack",
            {"task_key": "invite_teachers"},
            {"client_offline_id": "lp-ack-1"},
        )
        self.assertTrue(result["ok"])
        self.school.refresh_from_db()
        acks = (self.school.settings or {}).get("rmc_launch_playbook_acks") or {}
        self.assertIn("invite_teachers", acks)
        payload = build_launch_playbook(self.school)
        self.assertTrue(payload["visible"])
        done = [t for t in payload["tasks"] if t["key"] == "invite_teachers"]
        self.assertTrue(done and done[0]["done"])

    def test_discipline_refer_creates_incident(self):
        result = apply_tenant_journey_workflow(
            self.school.pk,
            self.teacher.pk,
            "discipline_refer",
            {
                "student_id": self.student.pk,
                "incident_type": Incident.Type.BEHAVIOR,
                "severity": Incident.Severity.LOW,
                "description": "Offline refer test",
            },
            {"client_offline_id": "disc-ref-1"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(
            Incident.objects.filter(school=self.school, student=self.student).count(),
            1,
        )

    def test_discipline_refer_idempotent_replay(self):
        payload = {"client_offline_id": "disc-ref-idem"}
        first = apply_tenant_journey_workflow(
            self.school.pk,
            self.teacher.pk,
            "discipline_refer",
            {"student_id": self.student.pk, "description": "First"},
            payload,
        )
        second = apply_tenant_journey_workflow(
            self.school.pk,
            self.teacher.pk,
            "discipline_refer",
            {"student_id": self.student.pk, "description": "Replay"},
            payload,
        )
        self.assertTrue(first["ok"])
        self.assertTrue(second.get("idempotent_replay"))
        self.assertEqual(Incident.objects.filter(school=self.school).count(), 1)

    def test_year_close_ack_persists(self):
        from apps.schools.year_close_checklist import build_year_close_checklist

        result = apply_tenant_journey_workflow(
            self.school.pk,
            self.admin.pk,
            "year_close_ack",
            {"item_key": "grades"},
            {"client_offline_id": "yc-ack-1"},
        )
        self.assertTrue(result["ok"])
        self.school.refresh_from_db()
        acks = (self.school.settings or {}).get("rmc_year_close_acks") or {}
        self.assertIn("grades", acks)
        # Checklist reads ack when year-close mode is active — handler path verified above.
        payload = build_year_close_checklist(self.school)
        self.assertIn("items", payload)
