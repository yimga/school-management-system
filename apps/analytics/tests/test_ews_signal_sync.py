"""N28: RiskFactor → StudentAtRiskSignal sync; intervention status updates."""

import uuid

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.analytics.models import InterventionLog, RiskFactor, StudentAtRiskSignal
from apps.analytics.views import at_risk_intervention_action
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership

User = get_user_model()


def _request_with_messages(request):
    SessionMiddleware(lambda r: None).process_request(request)
    setattr(request, "_messages", FallbackStorage(request))
    return request


class EwsSignalFromRiskFactorTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="EWS School",
            slug=f"ews-{uuid.uuid4().hex[:10]}",
            subdomain=f"ews-{uuid.uuid4().hex[:10]}",
        )
        self.portal_user = User.objects.create_user(
            username=f"stu-{uuid.uuid4().hex[:8]}",
            email=f"stu-{uuid.uuid4().hex[:8]}@t.test",
            password="x",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            user=self.portal_user,
            first_name="E",
            last_name="Student",
            student_code=f"sc-{uuid.uuid4().hex[:12]}",
            admission_number=f"ad-{uuid.uuid4().hex[:12]}",
        )

    def test_risk_factor_creates_signal_for_linked_student(self):
        self.assertFalse(
            StudentAtRiskSignal.objects.filter(school=self.school).exists()
        )
        RiskFactor.objects.create(
            school=self.school,
            student=self.student,
            score=72,
            reason_summary="Attendance dip",
        )
        sig = StudentAtRiskSignal.objects.get(
            school=self.school, student_user=self.portal_user
        )
        self.assertEqual(sig.status, StudentAtRiskSignal.Status.OPEN)
        self.assertGreaterEqual(float(sig.score), 72)
        self.assertIn("Attendance", sig.factors.get("reason", ""))

    def test_risk_factor_skips_unlinked_student(self):
        loose = StudentProfile.objects.create(
            school=self.school,
            first_name="N",
            last_name="User",
            student_code=f"sc2-{uuid.uuid4().hex[:12]}",
            admission_number=f"ad2-{uuid.uuid4().hex[:12]}",
        )
        RiskFactor.objects.create(
            school=self.school, student=loose, score=90, reason_summary="High risk"
        )
        self.assertFalse(StudentAtRiskSignal.objects.filter(school=self.school).exists())

    def test_intervention_start_marks_signal_in_intervention(self):
        RiskFactor.objects.create(
            school=self.school,
            student=self.student,
            score=80,
            reason_summary="Grades",
        )
        admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email=f"adm-{uuid.uuid4().hex[:8]}@t.test",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=admin, school=self.school, role="ADMIN", is_primary=True
        )
        req = _request_with_messages(
            RequestFactory().post(
                reverse("analytics:at_risk_intervention_action"),
                {
                    "action": "start",
                    "student_id": str(self.student.pk),
                    "action_taken": "Counselor",
                },
            )
        )
        req.user = admin
        req.school = self.school
        at_risk_intervention_action(req)
        sig = StudentAtRiskSignal.objects.get(student_user=self.portal_user)
        self.assertEqual(sig.status, StudentAtRiskSignal.Status.IN_INTERVENTION)

    def test_resolve_intervention_marks_signal_resolved(self):
        RiskFactor.objects.create(
            school=self.school,
            student=self.student,
            score=77,
            reason_summary="X",
        )
        log = InterventionLog.objects.create(
            school=self.school,
            student=self.student,
            trigger_reason="t",
            action_taken="a",
            status=InterventionLog.Status.ONGOING,
        )
        StudentAtRiskSignal.objects.filter(student_user=self.portal_user).update(
            status=StudentAtRiskSignal.Status.IN_INTERVENTION
        )
        admin = User.objects.create_user(
            username=f"adm2-{uuid.uuid4().hex[:8]}",
            email=f"adm2-{uuid.uuid4().hex[:8]}@t.test",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=admin, school=self.school, role="ADMIN", is_primary=True
        )
        req = _request_with_messages(
            RequestFactory().post(
                reverse("analytics:at_risk_intervention_action"),
                {"action": "resolve", "intervention_id": str(log.pk)},
            )
        )
        req.user = admin
        req.school = self.school
        at_risk_intervention_action(req)
        sig = StudentAtRiskSignal.objects.get(student_user=self.portal_user)
        self.assertEqual(sig.status, StudentAtRiskSignal.Status.RESOLVED)
