"""Magic UX: tenant app catalog strict single-primary CTA + grid anchor (HTTP)."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership

_HOST = "magicux-mkt.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _HOST],
    CONVERSION_SINGLE_ACTION_ENFORCED=True,
)
class TenantCatalogMagicUxStrictTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Magic UX Catalog School",
            slug="magicux-mkt",
            subdomain="magicux-mkt",
            is_active=True,
        )

    def _admin_client(self):
        u = User.objects.create_user(
            username=f"mux_admin_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="MUX1")
        SchoolMembership.objects.get_or_create(
            user=u,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        TOTPDevice.objects.create(user=u, name="test-device", confirmed=True)
        c = Client(HTTP_HOST=_HOST)
        c.login(username=u.username, password="x" * 8)
        session = c.session
        session["mfa_verified"] = True
        session.save()
        return c

    def test_strict_mode_primary_and_grid_markers(self):
        c = self._admin_client()
        url = reverse("tenant_app_catalog", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:600])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-tenant-catalog-primary="1"', body)
        self.assertIn('id="tenant-catalog-grid"', body)
        self.assertIn("rmc-conversion-more-actions", body)
