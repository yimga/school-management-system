"""Offline capability token mint — wire contract + TTL posture.

Locks the exact JS<->API contract that shipped broken for months: the
bootstrap refresh POSTed without ``device_id`` (required -> 400) and read
``capability_blob_b64`` while the server returns ``capability_blob``.
Companion static gate: scripts/verify_offline_auth_contract.py.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models_offline_device import DeviceRegistration, OfflineCapabilityToken
from apps.api.offline_device_api import OfflineTokenMintView
from apps.schools.models import School


class OfflineCapabilityMintTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Mint School", slug="mint-school")
        self.user = User.objects.create_user(username="mint_teacher", password="Test1234!")
        self.factory = APIRequestFactory()

    def _post(self, body, school=...):
        request = self.factory.post("/api/v1/devices/offline-token/", body, format="json")
        force_authenticate(request, user=self.user)
        if school is ...:
            request.school = self.school
        elif school is not None:
            request.school = school
        return OfflineTokenMintView.as_view()(request)

    def test_device_id_required(self):
        # The exact shape the broken bootstrap used to send. The platform
        # wraps validation errors in RFC-7807 problem details.
        response = self._post({"purpose": "offline_capability_refresh"})
        self.assertEqual(response.status_code, 400)
        fields = {e.get("field") for e in response.data.get("errors", [])}
        self.assertIn("device_id", fields)

    def test_school_required(self):
        response = self._post({"device_id": "web-tablet-001"}, school=None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("error"), "school_required")

    def test_mint_wire_contract_and_fingerprint_only_storage(self):
        response = self._post({"device_id": "web-tablet-001"})
        self.assertEqual(response.status_code, 201)
        # The exact keys the bootstrap JS reads — renaming any is a breaking
        # client change and must fail here first.
        for key in ("capability_blob", "expires_at", "permission_bitmap", "iam_snapshot"):
            self.assertIn(key, response.data)
        device = DeviceRegistration.objects.get(
            school=self.school, user=self.user, device_id="web-tablet-001"
        )
        token = OfflineCapabilityToken.objects.get(device=device)
        raw = response.data["capability_blob"]
        self.assertEqual(
            token.token_fingerprint, hashlib.sha256(raw.encode()).hexdigest()
        )
        # The raw token must never be persisted server-side.
        self.assertNotEqual(token.token_fingerprint, raw)
        self.assertTrue(token.is_valid)

    def test_ttl_default_is_12_hours(self):
        before = timezone.now()
        response = self._post({"device_id": "web-tablet-ttl"})
        self.assertEqual(response.status_code, 201)
        token = OfflineCapabilityToken.objects.get(device__device_id="web-tablet-ttl")
        self.assertGreater(token.expires_at, before + timedelta(hours=11))
        self.assertLess(token.expires_at, before + timedelta(hours=13))

    @override_settings(RMC_OFFLINE_CAPABILITY_TOKEN_TTL_HOURS=168)
    def test_ttl_is_settings_driven(self):
        # Long-offline campus posture: a deployment can extend the write
        # capability window without a code change.
        before = timezone.now()
        response = self._post({"device_id": "web-tablet-week"})
        self.assertEqual(response.status_code, 201)
        token = OfflineCapabilityToken.objects.get(device__device_id="web-tablet-week")
        self.assertGreater(token.expires_at, before + timedelta(hours=167))
        self.assertLess(token.expires_at, before + timedelta(hours=169))

    def test_remint_updates_device_not_duplicate(self):
        first = self._post({"device_id": "web-tablet-001"})
        second = self._post({"device_id": "web-tablet-001"})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(
            DeviceRegistration.objects.filter(
                school=self.school, user=self.user, device_id="web-tablet-001"
            ).count(),
            1,
        )
        # Each mint issues a fresh token against the same registration.
        self.assertEqual(
            OfflineCapabilityToken.objects.filter(
                device__device_id="web-tablet-001"
            ).count(),
            2,
        )
