"""Discipline incidents portal UI (metric 11)."""

import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.academics.models import Incident
from apps.academics.models_discipline import RestorativeAction
from apps.people.models import StudentProfile
from apps.portal.views_teacher import discipline_incidents_list
from apps.schools.models import School

User = get_user_model()


@override_settings(ROOT_URLCONF="config.tenant_urls")
class DisciplineIncidentsPortalTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Disc UI School",
            slug=f"discui-{uuid.uuid4().hex[:10]}",
            subdomain=f"discui-{uuid.uuid4().hex[:10]}",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Pat",
            last_name="Lee",
            student_code=f"ST-{uuid.uuid4().hex[:6]}",
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="d@ui.test",
            password="x",
            role="DISCIPLINE_MASTER",
        )
        Incident.objects.create(
            school=self.school,
            student=self.student,
            incident_type=Incident.Type.BEHAVIOR,
            severity=Incident.Severity.MEDIUM,
            date=date.today(),
            notify_parent=False,
        )

    def _req(self, method, path, data=None, user=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = user or self.admin
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_list_shows_incidents_with_points(self):
        resp = discipline_incidents_list(self._req("GET", "/discipline/"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Pat", content)
        self.assertIn("Restorative", content)

    def test_complete_restorative_action(self):
        ra = RestorativeAction.objects.filter(school=self.school).first()
        self.assertIsNotNone(ra)
        resp = discipline_incidents_list(
            self._req(
                "POST",
                "/discipline/",
                {
                    "action": "update_restorative",
                    "restorative_id": str(ra.pk),
                    "new_status": "completed",
                },
            )
        )
        self.assertEqual(resp.status_code, 302)
        ra.refresh_from_db()
        self.assertEqual(ra.status, RestorativeAction.Status.COMPLETED)
        self.assertIsNotNone(ra.completed_at)
