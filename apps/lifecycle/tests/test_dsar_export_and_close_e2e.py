"""Metric 19 — DSAR export + close tenant self-serve E2E (lifecycle surface).

Proves the wired ``dsar_export_and_close`` path: staff-only, school-scoped,
confirm-gated POST that enqueues wind-down export and (operator-only mode)
submits an offboarding request — without requiring live object storage.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.lifecycle.views_dsar import dsar_export_and_close
from apps.schools.models import School, SchoolMembership

User = get_user_model()


def _attach_session(request):
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


@override_settings(ROOT_URLCONF="config.tenant_urls")
class DsarExportAndCloseE2ETests(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"DSAR School {tag}",
            slug=f"dsar-{tag}",
            subdomain=f"dsar-{tag}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"dsar_admin_{tag}",
            password="Test1234",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.parent = User.objects.create_user(
            username=f"dsar_parent_{tag}",
            password="Test1234",
            role=User.Role.PARENT,
            is_staff=False,
        )
        self.rf = RequestFactory()

    def _req(self, method, user, data=None):
        if method == "POST":
            request = self.rf.post("/portal/configure/offboarding/export-and-close/", data or {})
        else:
            request = self.rf.get("/portal/configure/offboarding/export-and-close/")
        request.user = user
        request.school = self.school
        return _attach_session(request)

    def test_non_staff_forbidden(self):
        resp = dsar_export_and_close(self._req("GET", self.parent))
        self.assertEqual(resp.status_code, 403)

    def test_get_renders_confirmation(self):
        resp = dsar_export_and_close(self._req("GET", self.admin))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn(self.school.slug, body)

    def test_post_wrong_confirm_rejected(self):
        resp = dsar_export_and_close(
            self._req("POST", self.admin, {"confirm": "wrong-slug"})
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_operator_only_submits_request_and_exports(self):
        export = SimpleNamespace(archive_path="/tmp/export.zip", manifest_path=None)
        with (
            patch(
                "apps.schools.tenant_offboarding_policy.operator_only_offboarding",
                return_value=True,
            ),
            patch(
                "apps.schools.tenant_offboarding.run_wind_down_export",
                return_value=export,
            ) as mock_export,
            patch(
                "apps.schools.tenant_offboarding.request_tenant_offboarding",
            ) as mock_request,
        ):
            resp = dsar_export_and_close(
                self._req("POST", self.admin, {"confirm": self.school.slug})
            )
        self.assertEqual(resp.status_code, 200)
        mock_export.assert_called_once()
        mock_request.assert_called_once()
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Request submitted.", body)
        self.assertIn("portability export archive was generated", body.lower())
