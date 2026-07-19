"""N24: tenant activity log view."""

import uuid

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.views_tenant_observability import tenant_activity_log
from apps.platform_runtime.events import emit_platform_event
from apps.schools.models import School

User = get_user_model()


def _attach_session(request):
    SessionMiddleware(lambda _req: HttpResponse()).process_request(request)
    request.session.save()
    return request


class TenantActivityLogViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Log School",
            slug=f"lg-{uuid.uuid4().hex[:10]}",
            subdomain=f"lg-{uuid.uuid4().hex[:10]}",
        )
        self.admin = User.objects.create_user(
            username=f"a-{uuid.uuid4().hex[:8]}",
            email="a@t.test",
            password="x",
            role=User.Role.ADMIN,
        )
        self.factory = RequestFactory()

    def test_lists_events_for_school(self):
        emit_platform_event(
            "student_created",
            {"student_id": "1", "school_id": str(self.school.pk)},
            tenant_id=str(self.school.pk),
            school_id=self.school.pk,
        )
        req = self.factory.get("/backend/activity-log/")
        req.user = self.admin
        req.school = self.school
        _attach_session(req)
        resp = tenant_activity_log(req)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "student_created")

    def test_forbidden_non_leadership_teacher(self):
        from apps.accounts.models import User as U

        t = User.objects.create_user(
            username=f"te-{uuid.uuid4().hex[:8]}",
            email="te@t.test",
            password="x",
            role=U.Role.TEACHER,
        )
        req = self.factory.get("/")
        req.user = t
        req.school = self.school
        _attach_session(req)
        resp = tenant_activity_log(req)
        self.assertEqual(resp.status_code, 403)
