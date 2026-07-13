from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.platform_runtime.blueprint_contract import list_blueprints
from apps.platform_runtime.blueprint_preview import preview_blueprint
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
        TOTPDevice.objects.create(user=self.admin, name="test-device", confirmed=True)

    def _admin_client(self):
        client = Client(
            HTTP_HOST="tenant-blueprints.runmycampus.com",
            raise_request_exception=False,
        )
        client.login(username="tenant_blueprint_admin", password="x" * 8)
        session = client.session
        session["mfa_verified"] = True
        session.save()
        return client

    def test_school_admin_can_access_tenant_blueprint_setup(self):
        client = self._admin_client()

        response = client.get("/school/setup/blueprints/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("School Blueprint Setup", body)
        self.assertIn("Private Primary School", body)
        self.assertIn("Apply tenant blueprint", body)

    def test_tenant_user_cannot_see_platform_only_blueprint_management(self):
        client = self._admin_client()

        response = client.get("/school/setup/blueprints/")
        body = response.content.decode("utf-8", errors="replace")

        self.assertNotIn("Multi-campus Network", body)
        self.assertNotIn("/configuration/blueprints/", body)

    def test_tenant_apply_only_affects_own_school(self):
        client = self._admin_client()

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
        client = self._admin_client()

        response = client.get("/school/setup/blueprints/?blueprint=cameroon-gce-school&preview=1")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("live_payment_collection", body)

    def test_all_tenant_safe_blueprints_have_resolvable_pack_references(self):
        blocked = {}
        for blueprint in list_blueprints(tenant_safe_only=True):
            preview = preview_blueprint(
                blueprint["key"],
                school=self.school,
                actor=self.admin,
                platform_operator=False,
            )
            missing = [
                conflict
                for conflict in preview.get("conflicts", [])
                if conflict.get("code") == "pack_not_found"
            ]
            if missing:
                blocked[blueprint["key"]] = missing

        self.assertEqual(blocked, {})

    def test_blocked_blueprint_state_explains_reason(self):
        client = self._admin_client()

        response = client.get("/school/setup/blueprints/?blueprint=private-primary-school&preview=1")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Ready to apply", body)
        self.assertIn("Apply tenant blueprint", body)
        self.assertNotIn("Resolve blockers before apply", body)
