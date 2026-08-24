"""Tenant hosts must not hard-lock admins to profile while posture is weak."""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from unittest import mock

from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.middleware_minimum_security_strength import (
    MinimumSecurityStrengthMiddleware,
    _MINIMUM_STRENGTH_EXEMPT_PATH_PREFIXES,
)
from apps.accounts.models import User
from apps.schools.middleware import UrlConfSwitcherMiddleware
from apps.schools.models import School, SchoolMembership


@override_settings(
    SECURITY_ENFORCE_MINIMUM_STRENGTH=True,
    SINGLE_TENANT=True,
    USE_DJANGO_TENANTS=False,
    ROOT_URLCONF="config.tenant_urls",
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class TenantMinimumStrengthSoftLockTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Gilead Tech High",
            slug=f"gilead-{uuid.uuid4().hex[:6]}",
            subdomain=f"gilead-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:6]}",
            email="admin@gilead.test",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        User.objects.filter(pk=self.admin.pk).update(
            date_joined=timezone.now() - timedelta(days=30)
        )
        self.admin.refresh_from_db()
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
        )
        self.rf = RequestFactory()
        self.mw = MinimumSecurityStrengthMiddleware(lambda r: self._ok_response())

    @staticmethod
    def _ok_response():
        from django.http import HttpResponse

        return HttpResponse("ok")

    def _tenant_request(self, path: str, *, host: str = "gilead-tech.runmycampus.com"):
        request = self.rf.get(path, HTTP_HOST=host)
        UrlConfSwitcherMiddleware(lambda r: None).process_request(request)
        request.user = self.admin
        request.school = self.school
        return request

    def test_migration_cloud_path_is_exempt(self) -> None:
        path = "/school/setup/migration-cloud/bundle/1/quarantine/"
        self.assertTrue(any(path.startswith(p) for p in _MINIMUM_STRENGTH_EXEMPT_PATH_PREFIXES))
        response = self.mw(self._tenant_request(path))
        self.assertEqual(response.content, b"ok")

    def test_cloud_subdomain_allows_backend_dashboard_while_weak(self) -> None:
        response = self.mw(
            self._tenant_request(reverse("accounts:backend_dashboard"))
        )
        self.assertEqual(response.content, b"ok")

    def test_sovereign_ip_allows_backend_dashboard_while_weak(self) -> None:
        response = self.mw(
            self._tenant_request(
                reverse("accounts:backend_dashboard"),
                host="10.10.20.137:10000",
            )
        )
        self.assertEqual(response.content, b"ok")

    @override_settings(SINGLE_TENANT=False, ROOT_URLCONF="config.manager_urls")
    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"}, clear=False)
    def test_manager_host_still_hard_redirects_weak_admin(self) -> None:
        request = self.rf.get(
            reverse("accounts:backend_dashboard"),
            HTTP_HOST="manager.runmycampus.com",
        )
        UrlConfSwitcherMiddleware(lambda r: None).process_request(request)
        request.user = self.admin
        response = self.mw(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("profile", response["Location"])
