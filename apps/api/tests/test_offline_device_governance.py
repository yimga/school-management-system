"""Device governance — revocation is a capability, not just a field.

Locks the 9.8 device-governance wave (2026-07-02): before it, BOTH mint paths
hard-set ``revoked_at: None`` (a revoked/stolen device silently un-revoked
itself by re-minting) and no endpoint could revoke a device at all. These
tests assert the enforcement boundary end-to-end:

  * mint (API + offline-queue replay) refuses a revoked device,
  * mint no longer resurrects ``revoked_at``,
  * operator revoke cascades to outstanding capability tokens,
  * reinstate is the only path back, and is staff-only.

Companion static gate: scripts/verify_offline_auth_contract.py.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models_offline_device import DeviceRegistration, OfflineCapabilityToken
from apps.api.offline_device_api import OfflineTokenMintView
from apps.platform_runtime.offline_queue import _apply_provision_signup
from apps.portal.views_device_governance import (
    device_registration_reinstate,
    device_registration_revoke,
    device_registrations_index,
)
from apps.schools.models import School


class DeviceRevocationEnforcementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Gov School", slug="gov-school")
        self.user = User.objects.create_user(username="gov_teacher", password="Test1234!")
        self.staff = User.objects.create_user(
            username="gov_operator", password="Test1234!", is_staff=True
        )
        self.factory = APIRequestFactory()

    def _mint(self, device_id="gov-tablet-001"):
        request = self.factory.post(
            "/api/v1/devices/offline-token/", {"device_id": device_id}, format="json"
        )
        force_authenticate(request, user=self.user)
        request.school = self.school
        return OfflineTokenMintView.as_view()(request)

    def _register_revoked(self, device_id="gov-tablet-001"):
        return DeviceRegistration.objects.create(
            school=self.school,
            user=self.user,
            device_id=device_id,
            revoked_at=timezone.now(),
        )

    def test_mint_refuses_revoked_device(self):
        device = self._register_revoked()
        response = self._mint()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.get("error"), "device_revoked")
        device.refresh_from_db()
        # The mint attempt must not resurrect the registration.
        self.assertIsNotNone(device.revoked_at)
        self.assertFalse(OfflineCapabilityToken.objects.filter(device=device).exists())

    def test_offline_queue_signup_refuses_revoked_device(self):
        device = self._register_revoked()
        result = _apply_provision_signup(
            self.school.pk, self.user.pk, {"device_id": device.device_id}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "device_revoked")
        device.refresh_from_db()
        self.assertIsNotNone(device.revoked_at)

    def test_mint_still_works_for_active_device(self):
        response = self._mint("gov-tablet-fresh")
        self.assertEqual(response.status_code, 201)
        device = DeviceRegistration.objects.get(device_id="gov-tablet-fresh")
        self.assertTrue(device.is_active)


class DeviceGovernanceOperatorSurfaceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Gov School 2", slug="gov-school-2")
        self.user = User.objects.create_user(username="gov_teacher2", password="Test1234!")
        self.staff = User.objects.create_user(
            username="gov_operator2", password="Test1234!", is_staff=True
        )
        self.device = DeviceRegistration.objects.create(
            school=self.school, user=self.user, device_id="gov-tablet-ops"
        )
        self.token = OfflineCapabilityToken.objects.create(
            device=self.device,
            school=self.school,
            user=self.user,
            token_fingerprint="f" * 64,
            expires_at=timezone.now() + timedelta(hours=12),
        )

    def _post(self, view, body, user=None):
        from django.test import RequestFactory

        request = RequestFactory().post("/portal/super/devices/x/", body)
        request.user = user or self.staff
        # csrf_protect is satisfied by RequestFactory (test client semantics).
        request._dont_enforce_csrf_checks = True
        return view(request)

    def test_revoke_cascades_to_tokens(self):
        response = self._post(
            device_registration_revoke, {"device": str(self.device.pk), "format": "json"}
        )
        self.assertEqual(response.status_code, 200)
        self.device.refresh_from_db()
        self.token.refresh_from_db()
        self.assertIsNotNone(self.device.revoked_at)
        self.assertIsNotNone(self.token.revoked_at)
        self.assertFalse(self.token.is_valid)

    def test_reinstate_is_explicit_path_back(self):
        self.device.revoked_at = timezone.now()
        self.device.save(update_fields=["revoked_at"])
        response = self._post(
            device_registration_reinstate, {"device": str(self.device.pk), "format": "json"}
        )
        self.assertEqual(response.status_code, 200)
        self.device.refresh_from_db()
        self.assertIsNone(self.device.revoked_at)

    def test_non_staff_denied(self):
        response = self._post(
            device_registration_revoke,
            {"device": str(self.device.pk), "format": "json"},
            user=self.user,
        )
        # staff_member_required redirects non-staff to the admin login.
        self.assertEqual(response.status_code, 302)
        self.device.refresh_from_db()
        self.assertIsNone(self.device.revoked_at)

    def test_index_lists_devices_json(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/portal/super/devices/", {"format": "json"})
        request.user = self.staff
        response = device_registrations_index(request)
        self.assertEqual(response.status_code, 200)
        import json

        payload = json.loads(response.content)
        ids = {row["device_id"] for row in payload["rows"]}
        self.assertIn("gov-tablet-ops", ids)

    def test_unknown_device_404(self):
        response = self._post(
            device_registration_revoke,
            {"device": "00000000-0000-0000-0000-000000000000", "format": "json"},
        )
        self.assertEqual(response.status_code, 404)
