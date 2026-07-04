from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership


_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", _MGR_HOST],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class AdministrationModelTests(TestCase):
    def test_internal_admin_alias_preserves_admin_compatibility(self):
        client = Client(HTTP_HOST=_MGR_HOST, raise_request_exception=False)

        admin_response = client.get("/admin/")
        alias_response = client.get("/internal-admin/")

        self.assertNotEqual(admin_response.status_code, 404)
        self.assertEqual(alias_response.status_code, 302)
        self.assertEqual(alias_response["Location"], "/admin/")

    def test_tenant_configuration_opens_school_center_not_platform_configuration(self):
        school = School.objects.create(
            name="Tenant One",
            slug="tenant-one",
            subdomain="tenant-one",
            is_active=True,
        )
        tenant = Client(HTTP_HOST="tenant-one.runmycampus.com", raise_request_exception=False)
        user = User.objects.create_user(
            username="tenant_cfg_blocked",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=user,
            school=school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        TOTPDevice.objects.create(user=user, name="test-device", confirmed=True)
        tenant.login(username="tenant_cfg_blocked", password="x" * 8)
        session = tenant.session
        session["mfa_verified"] = True
        session.save()

        response = tenant.get("/configuration/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"rmc-school-configuration-center", response.content)
        self.assertNotIn(b"rmc-platform-configuration-center", response.content)
