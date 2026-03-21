"""Wave 16: visitor log ops module."""

import uuid

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.schoolops.models import VisitorCheckIn
from apps.schoolops.views_tenant_ops import ops_visitor_log
from apps.schools.models import School

User = get_user_model()


class TenantOpsWave16VisitorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Visitor School",
            slug=f"vis-{uuid.uuid4().hex[:10]}",
            subdomain=f"vis-{uuid.uuid4().hex[:10]}",
            features={"visitor_log": True},
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="a@v.test",
            password="x",
            role=User.Role.ADMIN,
        )

    def _req(self, method, path, data=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = self.admin
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_checkin_checkout(self):
        r = ops_visitor_log(
            self._req(
                "POST",
                "/v/",
                {
                    "action": "checkin",
                    "visitor_name": "Jane Guest",
                    "host_contact": "Principal",
                    "purpose": "Meeting",
                },
            )
        )
        self.assertEqual(r.status_code, 302)
        v = VisitorCheckIn.objects.get(school=self.school)
        self.assertIsNone(v.checked_out_at)
        r2 = ops_visitor_log(
            self._req(
                "POST",
                "/v/",
                {"action": "checkout", "visit_id": str(v.pk)},
            )
        )
        self.assertEqual(r2.status_code, 302)
        v.refresh_from_db()
        self.assertIsNotNone(v.checked_out_at)

    def test_visitor_feature_off_403(self):
        self.school.features = {"visitor_log": False}
        self.school.save(update_fields=["features"])
        resp = ops_visitor_log(self._req("GET", "/v/"))
        self.assertEqual(resp.status_code, 403)
