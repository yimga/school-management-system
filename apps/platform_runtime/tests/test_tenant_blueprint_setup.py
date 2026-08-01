from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.platform_runtime.blueprint_contract import get_blueprint, list_blueprints
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.models import BlueprintInstallation
from apps.schools.models import School, SchoolMembership


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
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
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
        self.assertNotIn("VariableDoesNotExist", body)

    def test_blueprint_template_never_reads_code_from_string_warnings(self):
        template = Path("templates/platform_runtime/tenant_blueprint_setup.html").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("warning.code", template)

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

    def test_tenant_safe_blueprints_expose_composition_and_app_catalog_guidance(self):
        missing = {}
        for blueprint in list_blueprints(tenant_safe_only=True):
            preview = preview_blueprint(
                blueprint["key"],
                school=self.school,
                actor=self.admin,
                platform_operator=False,
            )
            guidance = preview.get("composition_guidance") or {}
            if not guidance.get("role") or not guidance.get("education_tracks"):
                missing[blueprint["key"]] = guidance
            self.assertIn("app_catalog_recommendations", preview)

        self.assertEqual(missing, {})

    def test_ready_blueprint_state_shows_apply(self):
        client = self._admin_client()

        response = client.get("/school/setup/blueprints/?blueprint=private-primary-school&preview=1")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Ready to apply", body)
        self.assertIn("Apply tenant blueprint", body)
        self.assertNotIn("Resolve blockers before apply", body)

    def test_payment_blueprint_offers_a_route_to_100_and_records_it(self):
        # A payment-gated blueprint used to be pinned below 100 with no action a
        # tenant could take: the check read a static contract tuple. The page now
        # both explains the gate and carries the decision that closes it.
        #
        # Fixture is international-school, whose contract genuinely declares
        # multi_currency_settlement_external_required. This used to exercise
        # low-connectivity-school, which is no longer payment-gated at all: its
        # contract prescribes manual reconciliation, so the meter drops the check
        # and it reads 100 outright (see
        # test_blueprint_payment_model_coherence). Keeping that fixture would
        # have tested a route to 100 for a blueprint already at 100 — a guard
        # that can no longer fail.
        from apps.finance.fee_collection_posture import POSTURE_MANUAL, get_recorded_posture

        client = self._admin_client()

        before = client.get("/school/setup/blueprints/?blueprint=international-school")
        self.assertEqual(before.status_code, 200, msg=before.content[:400])
        body = before.content.decode("utf-8", errors="replace")
        self.assertIn("Fee collection posture", body)
        self.assertIn("Record manual reconciliation", body)
        self.assertEqual(before.context["blueprint_readiness"]["value"], 85)

        response = client.post(
            "/school/setup/blueprints/",
            {
                "action": "record_collection_posture",
                "blueprint": "international-school",
                "posture": POSTURE_MANUAL,
                "posture_note": "Cash collected at the bursary",
            },
        )

        self.assertEqual(response.status_code, 200, msg=response.content[:400])
        self.school.refresh_from_db()
        self.assertEqual(get_recorded_posture(self.school)["mode"], POSTURE_MANUAL)
        self.assertEqual(response.context["blueprint_readiness"]["value"], 100)
        self.assertEqual(response.context["blueprint_readiness"]["unmet"], [])
        # And no blueprint was applied by the posture form.
        self.assertFalse(BlueprintInstallation.objects.filter(school=self.school).exists())

    def test_posture_record_is_refused_without_finance_permission(self):
        from apps.finance.fee_collection_posture import POSTURE_MANUAL, get_recorded_posture

        client = self._admin_client()
        with patch(
            "apps.accounts.effective_access.permission_access", return_value=False
        ):
            response = client.post(
                "/school/setup/blueprints/",
                {
                    "action": "record_collection_posture",
                    "blueprint": "low-connectivity-school",
                    "posture": POSTURE_MANUAL,
                },
            )

        self.assertEqual(response.status_code, 403)
        self.school.refresh_from_db()
        self.assertEqual(get_recorded_posture(self.school), {})

    def test_blocked_blueprint_state_explains_reason(self):
        # Force a tenant-safe blueprint into preview_ready so the UI must explain
        # why Apply is disabled (not a silent empty-conflict block).
        client = self._admin_client()
        original = get_blueprint("private-primary-school")
        blocked = replace(original, status="preview_ready")

        with patch(
            "apps.platform_runtime.blueprint_preview.get_blueprint_or_raise",
            return_value=blocked,
        ):
            response = client.get(
                "/school/setup/blueprints/?blueprint=private-primary-school&preview=1"
            )

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Blocked", body)
        self.assertIn("Resolve blockers before apply", body)
        self.assertIn("Blueprint status is preview_ready.", body)
        self.assertNotIn("Ready to apply", body)
