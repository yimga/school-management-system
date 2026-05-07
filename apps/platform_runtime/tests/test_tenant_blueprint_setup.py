from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.platform_runtime.models import BlueprintInstallation
from apps.schools.models import School


@override_settings(
    ALLOWED_HOSTS=["*", "tenant-blueprints.runmycampus.com", "manager.runmycampus.com"],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class TenantBlueprintSetupTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Tenant Blueprints",
            slug="tenant-blueprints",
            subdomain="tenant-blueprints",
            is_active=True,
        )
        self.other = School.objects.create(
            name="Tenant Blueprints Other",
            slug="tenant-blueprints-other",
            subdomain="tenant-blueprints-other",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="tenant_blueprint_admin",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.platform = User.objects.create_user(
            username="tenant_blueprint_platform",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )

    def test_school_admin_can_access_tenant_blueprint_setup(self):
        client = Client(HTTP_HOST="tenant-blueprints.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_blueprint_admin", password="x" * 8)

        response = client.get("/school/setup/blueprints/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("School Blueprint Setup", body)
        self.assertIn("Private Primary School", body)

    def test_tenant_user_cannot_see_platform_only_blueprint_management(self):
        client = Client(HTTP_HOST="tenant-blueprints.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_blueprint_admin", password="x" * 8)

        response = client.get("/school/setup/blueprints/")
        body = response.content.decode("utf-8", errors="replace")

        self.assertNotIn("Multi-campus Network", body)
        self.assertNotIn("/configuration/blueprints/", body)

    def test_tenant_apply_only_affects_own_school(self):
        client = Client(HTTP_HOST="tenant-blueprints.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_blueprint_admin", password="x" * 8)

        response = client.post(
            "/school/setup/blueprints/",
            {"blueprint": "private-primary-school", "confirm": "yes"},
        )

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertTrue(
            BlueprintInstallation.objects.filter(
                school=self.school,
                blueprint_key="private-primary-school",
            ).exists()
        )
        self.assertFalse(BlueprintInstallation.objects.filter(school=self.other).exists())

    def test_external_blockers_remain_honest(self):
        client = Client(HTTP_HOST="tenant-blueprints.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_blueprint_admin", password="x" * 8)

        response = client.get("/school/setup/blueprints/?blueprint=cameroon-gce-school&preview=1")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("live_payment_collection", body)
