"""BR-06 at-risk intervention POST workflow."""

import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.analytics.models import InterventionLog, RiskFactor
from apps.analytics.views import at_risk_intervention_action
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class AtRiskInterventionActionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Risk School",
            slug=f"rs-{uuid.uuid4().hex[:10]}",
            subdomain=f"rs-{uuid.uuid4().hex[:10]}",
        )
        self.user = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}@t.test",
            email=f"adm-{uuid.uuid4().hex[:8]}@t.test",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="R",
            last_name="Student",
            student_code=f"sr-{uuid.uuid4().hex[:12]}",
            admission_number=f"ar-{uuid.uuid4().hex[:12]}",
        )
        RiskFactor.objects.create(
            school=self.school,
            student=self.student,
            score=85,
            reason_summary="Attendance",
        )

    def test_start_intervention_creates_log(self):
        req = self.factory.post(
            "/analytics/at-risk/intervention/",
            {
                "action": "start",
                "student_id": str(self.student.pk),
                "action_taken": "Counselor scheduled",
            },
        )
        req.user = self.user
        req.school = self.school
        resp = at_risk_intervention_action(req)
        self.assertEqual(resp.status_code, 302)
        log = InterventionLog.objects.filter(
            school=self.school, student=self.student
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, InterventionLog.Status.ONGOING)
        self.assertIn("Counselor", log.action_taken)

    def test_resolve_intervention(self):
        log = InterventionLog.objects.create(
            school=self.school,
            student=self.student,
            trigger_reason="t",
            action_taken="call",
            status=InterventionLog.Status.ONGOING,
        )
        req = self.factory.post(
            "/analytics/at-risk/intervention/",
            {"action": "resolve", "intervention_id": str(log.pk)},
        )
        req.user = self.user
        req.school = self.school
        at_risk_intervention_action(req)
        log.refresh_from_db()
        self.assertEqual(log.status, InterventionLog.Status.RESOLVED)
        self.assertIsNotNone(log.resolved_at)
