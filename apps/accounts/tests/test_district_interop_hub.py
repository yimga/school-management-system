"""Tenant District & LMS interop hub."""

import os
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.views_district_interop import district_lms_interop
from apps.integrations_marketplace.models import ServiceIntegration
from apps.interop.oneroster.constants import ONEROSTER_DISTRICT_API_SERVICE_NAME
from apps.schools.models import School, TenantInteropAccessLog


class DistrictInteropHubTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Interop School",
            slug="interop-sch",
            subdomain="interop-sch",
            is_active=True,
        )
        self.admin = User.objects.create_user(username="interop_adm", password="x")
        self.admin.role = User.Role.ADMIN
        self.admin.save(update_fields=["role"])
        self.teacher = User.objects.create_user(username="interop_t", password="x")
        self.teacher.role = User.Role.TEACHER
        self.teacher.save(update_fields=["role"])

    def test_teacher_forbidden(self):
        req = self.factory.get("/authentication/backend/district-lms-interop/")
        req.user = self.teacher
        req.school = self.school
        resp = district_lms_interop(req)
        self.assertEqual(resp.status_code, 403)

    def test_admin_renders(self):
        req = self.factory.get("/authentication/backend/district-lms-interop/")
        req.user = self.admin
        req.school = self.school
        resp = district_lms_interop(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"OneRoster", resp.content)
        self.assertIn(b"Interop workbench", resp.content)
        self.assertIn(b"Connector access log", resp.content)
        self.assertIn(b"Native Clever", resp.content)
        self.assertEqual(resp.content.count(b"data-rmc-password-toggle"), 3)

    @override_settings(ALLOWED_HOSTS=["*"])
    @patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False)
    def test_save_native_vendor_persists_config(self):
        host = f"{self.school.subdomain}.example.com"
        c = Client(HTTP_HOST=host)
        c.force_login(self.admin)
        url = reverse("accounts:district_interop_save_native_vendor")
        r = c.post(
            url,
            {
                "native_clever_bearer": "clever-token-abcdefghij",
                "native_classlink_bearer": "",
                "native_classlink_base_url": "https://oneroster.classlink.example/v1p1",
            },
            secure=True,
        )
        self.assertEqual(r.status_code, 302)
        si = ServiceIntegration.objects.get(
            school=self.school,
            service_name=ONEROSTER_DISTRICT_API_SERVICE_NAME,
        )
        self.assertEqual(si.config.get("native_clever_bearer"), "clever-token-abcdefghij")
        self.assertEqual(
            si.config.get("native_classlink_base_url"),
            "https://oneroster.classlink.example/v1p1",
        )

    @override_settings(ALLOWED_HOSTS=["*"])
    @patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False)
    def test_native_probe_without_tokens_warns(self):
        host = f"{self.school.subdomain}.example.com"
        c = Client(HTTP_HOST=host)
        c.force_login(self.admin)
        r = c.post(
            reverse("accounts:district_interop_native_probe"),
            follow=True,
            secure=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"No native Clever", r.content)

    @override_settings(ALLOWED_HOSTS=["*"])
    @patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False)
    @patch("apps.interop.clever_classlink_client.clever_list_users", return_value={})
    @patch("apps.interop.clever_classlink_client.clever_list_schools", return_value={})
    @patch("apps.interop.clever_classlink_client.clever_list_sections", return_value={})
    def test_native_probe_with_clever_token_writes_access_log(
        self, _sec, _sch, _users
    ):
        host = f"{self.school.subdomain}.example.com"
        c = Client(HTTP_HOST=host)
        c.force_login(self.admin)
        c.post(
            reverse("accounts:district_interop_save_native_vendor"),
            {"native_clever_bearer": "x" * 24},
            secure=True,
        )
        before = TenantInteropAccessLog.objects.filter(
            school=self.school, service="native_vendor"
        ).count()
        r = c.post(
            reverse("accounts:district_interop_native_probe"),
            follow=True,
            secure=True,
        )
        self.assertEqual(r.status_code, 200)
        after = TenantInteropAccessLog.objects.filter(
            school=self.school, service="native_vendor"
        ).count()
        self.assertGreater(after, before)
        self.assertIn(b"clever", r.content.lower())

    def test_anonymous_forbidden(self):
        req = self.factory.get("/authentication/backend/district-lms-interop/")
        req.user = AnonymousUser()
        req.school = self.school
        resp = district_lms_interop(req)
        self.assertIn(resp.status_code, (302, 403))
