"""FAIL-CLOSED tenant decorators on high-risk export and operator routes."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission
from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership

_T_HOST = "abs-sec.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _T_HOST])
class AbsoluteSecurityExportTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.school = School.objects.create(
            name="Abs Sec",
            slug="abs-sec",
            subdomain="abs-sec",
            is_active=True,
        )

    def _force_login_verified(self, client: Client, user: User) -> None:
        TOTPDevice.objects.get_or_create(
            user=user,
            name="default",
            defaults={"confirmed": True},
        )
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session.save()

    def test_compliance_download_403_without_membership(self):
        u = User.objects.create_user(
            username=f"n_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm)
        c = Client(HTTP_HOST=_T_HOST)
        self._force_login_verified(c, u)
        url = reverse(
            "siteconfig:compliance_export_download",
            kwargs={"export_key": "waec_wassce_student_summary"},
            urlconf="config.tenant_urls",
        )
        r = c.get(url)
        self.assertEqual(r.status_code, 403)

    def test_compliance_download_succeeds_with_membership_and_export_perm(self):
        u = User.objects.create_user(
            username=f"y_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm)
        SchoolMembership.objects.create(
            user=u, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        c = Client(HTTP_HOST=_T_HOST)
        self._force_login_verified(c, u)
        url = reverse(
            "siteconfig:compliance_export_download",
            kwargs={"export_key": "waec_wassce_student_summary"},
            urlconf="config.tenant_urls",
        )
        r = c.get(url, follow=False)
        self.assertIn(r.status_code, (200, 302), msg=r.content[:500])

    def test_parent_cannot_export_compliance(self):
        u = User.objects.create_user(
            username=f"p_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            role=User.Role.PARENT,
        )
        SchoolMembership.objects.create(
            user=u, school=self.school, role=User.Role.PARENT, is_primary=True
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)
        url = reverse("siteconfig:compliance_exports", urlconf="config.tenant_urls")
        self.assertEqual(c.get(url).status_code, 403)
