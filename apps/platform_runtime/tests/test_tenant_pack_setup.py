from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.platform_runtime.models import PackInstallation
from apps.schools.models import School


@override_settings(
    ALLOWED_HOSTS=["*", "tenant-packs.runmycampus.com", "manager.runmycampus.com"],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class TenantPackSetupTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Tenant Packs", slug="tenant-packs", subdomain="tenant-packs", is_active=True)
        self.other = School.objects.create(name="Tenant Packs Other", slug="tenant-packs-other", subdomain="tenant-packs-other", is_active=True)
        self.admin = User.objects.create_user(username="tenant_pack_admin", password="x" * 8, role=User.Role.ADMIN, is_staff=True)

    def test_school_admin_can_access_tenant_pack_setup(self):
        client = Client(HTTP_HOST="tenant-packs.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_pack_admin", password="x" * 8)

        response = client.get("/school/setup/packs/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Pack setup", body)
        self.assertIn("Attendance Recovery", body)

    def test_tenant_apply_only_affects_own_school(self):
        client = Client(HTTP_HOST="tenant-packs.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_pack_admin", password="x" * 8)

        response = client.post("/school/setup/packs/", {"pack": "attendance-recovery", "pack_type": "workflow_pack", "confirm": "yes"})

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertTrue(PackInstallation.objects.filter(school=self.school, pack_key="attendance-recovery").exists())
        self.assertFalse(PackInstallation.objects.filter(school=self.other).exists())

    def test_external_blockers_remain_honest(self):
        client = Client(HTTP_HOST="tenant-packs.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_pack_admin", password="x" * 8)

        response = client.get("/school/setup/packs/?pack=finance-approval&pack_type=policy_bundle&preview=1")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertIn("Finance Approval", response.content.decode("utf-8", errors="replace"))
