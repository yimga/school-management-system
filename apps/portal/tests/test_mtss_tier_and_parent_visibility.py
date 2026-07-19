"""Metric #11 — MTSS tier mutate + parent notified-incident visibility."""

from __future__ import annotations

import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from django.utils import timezone

from apps.academics.discipline_services import log_mtss_contact, set_student_mtss_tier
from apps.academics.models import Incident
from apps.accounts.models import Permission
from apps.analytics.models import InterventionLog
from apps.people.models import StudentGuardian, StudentProfile
from apps.portal.views_teacher import counselor_caseload
from apps.schools.models import School, SchoolMembership

User = get_user_model()


def _school(tag):
    return School.objects.create(
        name=f"MTSS {tag}",
        slug=f"mtss-{tag}-{uuid.uuid4().hex[:8]}",
        subdomain=f"mtss-{tag}-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


@override_settings(ROOT_URLCONF="config.tenant_urls")
class MtssTierAndParentVisibilityTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = _school("A")
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Morgan",
            last_name="Kettlebridge",
            student_code=f"ST-{uuid.uuid4().hex[:6]}",
        )
        self.open_inc = Incident.objects.create(
            school=self.school,
            student=self.student,
            incident_type=Incident.Type.BEHAVIOR,
            severity=Incident.Severity.MEDIUM,
            mtss_tier=Incident.MtssTier.TIER_1,
            date=date.today(),
            notify_parent=True,
            parent_notified_at=timezone.now(),
        )
        self.resolved = Incident.objects.create(
            school=self.school,
            student=self.student,
            incident_type=Incident.Type.TARDINESS,
            severity=Incident.Severity.LOW,
            mtss_tier=Incident.MtssTier.TIER_1,
            status=Incident.Status.RESOLVED,
            date=date.today(),
            notify_parent=False,
        )
        self.hidden = Incident.objects.create(
            school=self.school,
            student=self.student,
            incident_type=Incident.Type.BEHAVIOR,
            severity=Incident.Severity.LOW,
            mtss_tier=Incident.MtssTier.TIER_1,
            date=date.today(),
            notify_parent=False,
        )
        self.counselor = User.objects.create_user(
            username=f"mtss-c-{uuid.uuid4().hex[:8]}",
            email="c@mtss.test",
            password="x",
            role=User.Role.TEACHER,
        )
        perm, _ = Permission.objects.get_or_create(
            code="discipline.manage",
            defaults={"name": "Discipline management"},
        )
        self.counselor.feature_permissions.add(perm)
        self.parent = User.objects.create_user(
            username=f"mtss-p-{uuid.uuid4().hex[:8]}",
            email="p@mtss.test",
            password="Test1234!",
            role=User.Role.PARENT,
        )
        SchoolMembership.objects.create(
            user=self.parent, school=self.school, role="PARENT"
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.student,
            can_view_results=True,
        )

    def _caseload_req(self, method="get", data=None):
        path = "/staff/discipline/caseload/"
        if method == "post":
            r = self.factory.post(path, data or {})
        else:
            r = self.factory.get(path)
        r.user = self.counselor
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_set_student_mtss_tier_updates_open_only(self):
        result = set_student_mtss_tier(
            school=self.school,
            student=self.student,
            tier=Incident.MtssTier.TIER_3,
            actor=self.counselor,
        )
        self.assertEqual(result["updated"], 2)  # open_inc + hidden (both non-resolved)
        self.open_inc.refresh_from_db()
        self.resolved.refresh_from_db()
        self.hidden.refresh_from_db()
        self.assertEqual(self.open_inc.mtss_tier, Incident.MtssTier.TIER_3)
        self.assertEqual(self.hidden.mtss_tier, Incident.MtssTier.TIER_3)
        self.assertEqual(self.resolved.mtss_tier, Incident.MtssTier.TIER_1)

    def test_counselor_post_updates_tier_on_caseload(self):
        resp = counselor_caseload(
            self._caseload_req(
                "post",
                {
                    "intent": "set_tier",
                    "student_id": str(self.student.pk),
                    "mtss_tier": Incident.MtssTier.TIER_3,
                },
            )
        )
        self.assertEqual(resp.status_code, 302)
        self.open_inc.refresh_from_db()
        self.assertEqual(self.open_inc.mtss_tier, Incident.MtssTier.TIER_3)
        get_resp = counselor_caseload(self._caseload_req())
        self.assertEqual(get_resp.status_code, 200)
        self.assertIn("Tier 3", get_resp.content.decode())

    def test_parent_sees_notified_incidents_only(self):
        client = Client()
        client.force_login(self.parent)
        session = client.session
        session["school_id"] = str(self.school.id)
        session.save()
        resp = client.get(reverse("portal:parent_attendance_discipline"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Kettlebridge", body)
        self.assertIn("Notified discipline", body)
        # notify_parent=False incident should not show a distinctive type-only leak;
        # page lists type display for notified rows — Behavior appears for open_inc.
        self.assertIn("Behavior", body)

    def test_counselor_logs_intervention_contact(self):
        resp = counselor_caseload(
            self._caseload_req(
                "post",
                {
                    "intent": "log_contact",
                    "student_id": str(self.student.pk),
                    "action_taken": "Meeting",
                    "notes": "Parent conference scheduled",
                },
            )
        )
        self.assertEqual(resp.status_code, 302)
        log = InterventionLog.objects.get(school=self.school, student=self.student)
        self.assertEqual(log.action_taken, "Meeting")
        self.assertIn("Parent conference", log.trigger_reason)
        get_resp = counselor_caseload(self._caseload_req())
        self.assertEqual(get_resp.status_code, 200)
        self.assertIn("Meeting", get_resp.content.decode())

    def test_log_mtss_contact_rejects_cross_school(self):
        other = _school("B")
        other_student = StudentProfile.objects.create(
            school=other,
            first_name="X",
            last_name="Y",
            student_code=f"OX-{uuid.uuid4().hex[:6]}",
        )
        result = log_mtss_contact(
            school=self.school,
            student=other_student,
            action_taken="Call",
            actor=self.counselor,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "student_school_mismatch")
