"""End-to-end proof that tenant self-rollback is reachable by a REAL tenant admin.

The companion suite (``test_tenant_blueprint_rollback_view``) calls the view
function directly with a ``create_superuser`` actor. That is a useful unit test
but it cannot prove the feature works, for two reasons:

1. ``tenant_operator_hub_eligible`` returns ``True`` on its FIRST branch for a
   superuser, so a superuser-only test exercises none of the tenant-admin logic
   beneath it. A school's real admin carries ``role=ADMIN`` and is **not**
   necessarily ``is_staff`` — that exact mismatch is what made the tenant
   workflow engine unreachable in the 2026-08-03 access audit. A gate that
   admits only superusers looks green in tests and is dead in production, so
   this fixture pins ``is_staff=False`` deliberately.
2. Calling the view callable directly bypasses URL routing, ``@login_required``,
   session auth, CSRF, and the tenant-host middleware stack
   (``OperatorTenantConfinementMiddleware`` + ``RequireMFAMiddleware``). A route
   registered on the wrong urlconf still passes such a test.

So these drive the real client over the tenant host: the button must RENDER for
an applied installation, the POST must retract the blueprint AND its child
packs, and an end-user role must be refused.
"""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.models import BlueprintInstallation, PackInstallation
from apps.schools.models import School, SchoolMembership

BLUEPRINT = "private-primary-school"
HOST = "tenant-rollback-e2e.runmycampus.com"
PASSWORD = "x" * 8
SETUP_PATH = "/school/setup/blueprints/"


@override_settings(
    ALLOWED_HOSTS=["*", HOST],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_PINNING_ENABLED=False,
)
class TenantBlueprintRollbackEndToEndTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Tenant Rollback E2E",
            slug="tenant-rollback-e2e",
            subdomain="tenant-rollback-e2e",
            is_active=True,
        )
        # A REAL tenant admin: role=ADMIN, deliberately NOT is_staff and NOT a
        # superuser — the shape the platform actually mints for a school owner.
        self.admin = User.objects.create_user(
            username="tenant_rollback_admin",
            password=PASSWORD,
            role=User.Role.ADMIN,
        )
        self.assertFalse(self.admin.is_staff)
        self.assertFalse(self.admin.is_superuser)
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        TOTPDevice.objects.create(
            user=self.admin, name="test-device-rollback", confirmed=True
        )

    def _client_for(self, username):
        client = Client(HTTP_HOST=HOST, raise_request_exception=False)
        self.assertTrue(
            client.login(username=username, password=PASSWORD),
            f"tenant login failed for {username!r}",
        )
        session = client.session
        session["mfa_verified"] = True
        session.save()
        return client

    def _apply(self):
        apply_blueprint(
            BLUEPRINT,
            school=self.school,
            actor=None,
            confirmed=True,
            platform_operator=True,
        )
        installation = (
            BlueprintInstallation.objects.filter(school=self.school)
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(installation)
        return installation

    def _rollback_path(self, installation):
        return f"{SETUP_PATH}installations/{installation.id}/rollback/"

    def test_a_real_tenant_admin_is_admitted_by_the_gate(self):
        """Must-fire: an is_staff-shaped gate would refuse this user."""
        from apps.accounts.permissions import tenant_operator_hub_eligible

        self.assertTrue(
            tenant_operator_hub_eligible(self.admin),
            "a role=ADMIN tenant admin (is_staff=False) cannot reach self-rollback",
        )

    def test_rollback_button_renders_for_an_applied_installation(self):
        installation = self._apply()
        response = self._client_for(self.admin.username).get(SETUP_PATH)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            self._rollback_path(installation),
            response.content.decode(),
            "the applied installation renders no rollback affordance for the tenant",
        )

    def test_post_over_the_tenant_host_retracts_blueprint_and_child_packs(self):
        installation = self._apply()
        self.assertGreater(
            installation.pack_installations.filter(
                status=PackInstallation.Status.APPLIED
            ).count(),
            0,
            "precondition: the blueprint installed child packs",
        )
        response = self._client_for(self.admin.username).post(
            self._rollback_path(installation), {"confirm": "yes"}
        )
        self.assertEqual(response.status_code, 302)
        installation.refresh_from_db()
        self.assertEqual(installation.status, BlueprintInstallation.Status.ROLLED_BACK)
        still_applied = list(
            installation.pack_installations.filter(
                status=PackInstallation.Status.APPLIED
            ).values_list("pack_key", flat=True)
        )
        self.assertEqual(
            still_applied,
            [],
            f"tenant rollback left these packs enforcing: {still_applied}",
        )

    def test_an_end_user_role_cannot_roll_back_over_the_tenant_host(self):
        installation = self._apply()
        parent = User.objects.create_user(
            username="tenant_rollback_parent",
            password=PASSWORD,
            role=User.Role.PARENT,
        )
        SchoolMembership.objects.create(
            user=parent,
            school=self.school,
            role=User.Role.PARENT,
            is_primary=True,
        )
        response = self._client_for(parent.username).post(
            self._rollback_path(installation), {"confirm": "yes"}
        )
        self.assertNotEqual(
            response.status_code,
            302,
            "a parent reached the rollback redirect path",
        )
        installation.refresh_from_db()
        self.assertEqual(
            installation.status,
            BlueprintInstallation.Status.APPLIED,
            "a parent rolled back the school's blueprint",
        )
