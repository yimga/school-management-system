"""The pack setup page must be able to reach 100 readiness in place.

172 of 174 packs score 100 unconditionally. The remaining two policy bundles
(``finance-approval``, ``low-connectivity-attendance``) carry a live-payment
*go-live* gate, so they read 80 for any tenant that has neither connected a
payment rail nor recorded how it collects fees.

That is honest, but it was a dead end: the shortfall was named on the pack page
("Pending: Live payment onboarding") while the control that resolves it existed
only on the blueprint and finance surfaces. A meter that reports an unmet item
the page offers no way to act on is not actionable — it is just a number that
never moves.

These tests pin the whole closure loop on the pack surface itself: the gate is
visible, the control is offered, recording works, permission is enforced, and the
re-rendered page reflects the new state rather than the pre-POST world.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.finance.fee_collection_posture import (
    POSTURE_MANUAL,
    resolve_live_collection_state,
)
from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.pack_preview import preview_pack
from apps.platform_runtime.readiness_meters import pack_readiness
from apps.schools.models import School, SchoolMembership

PACK = "finance-approval"
PACK_TYPE = "policy_bundle"
SETUP_URL = "/school/setup/packs/"
HOST = "pack-readiness.runmycampus.com"


class PackReadinessCeilingTests(TestCase):
    """Engine level: the ceiling is reachable, and only by a real decision."""

    def setUp(self):
        self.school = School.objects.create(
            name="Pack Ceiling School",
            slug="pack-ceiling-school",
            subdomain="pack-ceiling-school",
            is_active=True,
        )

    def _readiness(self):
        preview = preview_pack(
            PACK, pack_type=PACK_TYPE, school=self.school, platform_operator=False
        )
        return pack_readiness(preview, school=self.school)

    def test_gate_is_open_before_the_tenant_decides(self):
        readiness = self._readiness()

        self.assertEqual(readiness["value"], 80)
        self.assertEqual(readiness["unmet"], ["Live payment onboarding"])
        self.assertEqual(resolve_live_collection_state(self.school)["state"], "pending")

    def test_recording_a_manual_posture_reaches_100(self):
        from apps.finance.fee_collection_posture import record_collection_posture

        record_collection_posture(self.school, mode=POSTURE_MANUAL, note="cash and MoMo")
        self.school.refresh_from_db()

        readiness = self._readiness()

        self.assertEqual(readiness["value"], 100)
        self.assertTrue(readiness["complete"])
        self.assertEqual(readiness["unmet"], [])

    def test_the_ceiling_is_not_reachable_by_doing_nothing(self):
        """Must-fire: silence must never be read as a settled posture."""
        other = School.objects.create(
            name="Untouched School",
            slug="untouched-school",
            subdomain="untouched-school",
            is_active=True,
        )
        preview = preview_pack(
            PACK, pack_type=PACK_TYPE, school=other, platform_operator=False
        )

        self.assertEqual(pack_readiness(preview, school=other)["value"], 80)


@override_settings(
    ALLOWED_HOSTS=["*", HOST, "manager.runmycampus.com"],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class PackSetupPosturePanelTests(TestCase):
    """Surface level: the page shows the gate and can close it in place."""

    def setUp(self):
        self.school = School.objects.create(
            name="Pack Readiness",
            slug="pack-readiness",
            subdomain="pack-readiness",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="pack_readiness_admin",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        TOTPDevice.objects.create(user=self.admin, name="test-device", confirmed=True)

    def _client(self):
        client = Client(HTTP_HOST=HOST, raise_request_exception=False)
        client.login(username="pack_readiness_admin", password="x" * 8)
        session = client.session
        session["mfa_verified"] = True
        session.save()
        return client

    def test_page_offers_the_posture_control_while_the_gate_is_open(self):
        response = self._client().get(f"{SETUP_URL}?pack={PACK}&pack_type={PACK_TYPE}")

        self.assertEqual(response.status_code, 200, msg=response.content[:400])
        self.assertEqual(response.context["pack_readiness"]["value"], 80)
        self.assertContains(response, 'data-pack-collection-posture="1"')
        self.assertContains(response, "record_collection_posture")

    def test_recording_from_the_pack_page_moves_the_meter_in_the_same_response(self):
        response = self._client().post(
            SETUP_URL,
            {
                "action": "record_collection_posture",
                "pack": PACK,
                "pack_type": PACK_TYPE,
                "posture": POSTURE_MANUAL,
                "posture_note": "cash and bank transfer",
            },
        )

        self.assertEqual(response.status_code, 200, msg=response.content[:400])
        # The re-rendered page must reflect the mutation, not the pre-POST world.
        self.assertEqual(response.context["pack_readiness"]["value"], 100)
        self.assertTrue(response.context["pack_readiness"]["complete"])
        self.assertEqual(
            response.context["collection_posture"]["state"], "manual_recorded"
        )
        self.assertNotContains(response, 'data-pack-collection-posture="1"')
        # The posture form must not have installed anything.
        self.assertFalse(PackInstallation.objects.filter(school=self.school).exists())

    def test_posture_panel_disappears_once_settled(self):
        from apps.finance.fee_collection_posture import record_collection_posture

        record_collection_posture(self.school, mode=POSTURE_MANUAL, actor=self.admin)
        self.school.refresh_from_db()

        response = self._client().get(f"{SETUP_URL}?pack={PACK}&pack_type={PACK_TYPE}")

        self.assertEqual(response.context["pack_readiness"]["value"], 100)
        self.assertNotContains(response, 'data-pack-collection-posture="1"')

    def test_a_pack_with_no_payment_gate_is_already_at_100(self):
        response = self._client().get(
            f"{SETUP_URL}?pack=attendance-recovery&pack_type=workflow_pack"
        )

        self.assertEqual(response.status_code, 200, msg=response.content[:400])
        self.assertEqual(response.context["pack_readiness"]["value"], 100)
        self.assertNotContains(response, 'data-pack-collection-posture="1"')

    def test_posture_record_is_refused_without_finance_permission(self):
        """Recording how a school collects money stays a finance decision."""
        from apps.finance.fee_collection_posture import get_recorded_posture

        with patch(
            "apps.accounts.effective_access.permission_access", return_value=False
        ):
            response = self._client().post(
                SETUP_URL,
                {
                    "action": "record_collection_posture",
                    "pack": PACK,
                    "pack_type": PACK_TYPE,
                    "posture": POSTURE_MANUAL,
                },
            )

        self.assertEqual(response.status_code, 403)
        self.school.refresh_from_db()
        self.assertEqual(get_recorded_posture(self.school), {})
