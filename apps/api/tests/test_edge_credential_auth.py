"""Edge machine credential -> receiver auth (Tier 3 Slice 3).

A sovereign box POSTs a bundle with Authorization: Bearer <edge-credential> and NO
session / subdomain. EdgeCredentialAuthentication must resolve the credential to the
bound (user, school), scope the request, and let the receiver persist — and must
reject a missing / garbage / revoked / non-edge-scope token.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.accounts.models_offline_device import DeviceRegistration, OfflineCapabilityToken
from apps.api.sync_bundle_api import SyncBundleUploadView
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import export_delta_bundle
from apps.sync_engine.edge_outbox import mint_edge_credential

_SIGN_KEY = "edge-auth-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class EdgeCredentialAuthReceiverTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"EdgeAuth {uid}", slug=f"edgeauth-{uid}", subdomain=f"edgeauth{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"edge_svc_{uid}", password="Test1234", email=f"e{uid}@test.com"
        )
        SchoolMembership.objects.create(user=self.user, school=self.school, role="ADMIN", is_primary=True)
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Njoya", date_of_birth="2012-01-01"
        )
        self.rf = APIRequestFactory()
        self.raw_token, self.token_obj = mint_edge_credential(
            self.school, self.user, device_id="edge-box-1", days=30
        )

    def _bundle(self, first_name="EdgeName"):
        future = (timezone.now() + timedelta(minutes=10)).isoformat()
        return export_delta_bundle(
            school_id=str(self.school.id),
            rows=[{"entity_type": "student", "id": self.student.pk, "changes": {"first_name": first_name}, "updated_at": future}],
            device_id="edge-box-1",
        )

    def _post(self, bundle, auth=None):
        extra = {"HTTP_AUTHORIZATION": auth} if auth is not None else {}
        # NB: no request.school (no subdomain) and no force_authenticate — the token must do it.
        request = self.rf.post(
            "/api/v1/sync/bundle/upload/",
            data=bundle,
            content_type="application/x-rmc-sync-bundle+ndjson",
            **extra,
        )
        return SyncBundleUploadView.as_view()(request)

    def test_valid_edge_credential_authenticates_and_persists(self):
        resp = self._post(self._bundle("EdgeName"), auth=f"Bearer {self.raw_token}")
        self.assertEqual(resp.status_code, 200, getattr(resp, "data", None))
        self.assertTrue(resp.data["ok"])
        self.assertEqual(resp.data["applied"], 1)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "EdgeName")

    def test_missing_credential_is_unauthorized(self):
        resp = self._post(self._bundle(), auth=None)
        self.assertIn(resp.status_code, (401, 403))
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Ada")

    def test_garbage_bearer_is_unauthorized(self):
        resp = self._post(self._bundle(), auth="Bearer not-a-real-token")
        self.assertIn(resp.status_code, (401, 403))

    def test_revoked_device_credential_rejected(self):
        self.token_obj.device.revoked_at = timezone.now()
        self.token_obj.device.save(update_fields=["revoked_at"])
        resp = self._post(self._bundle(), auth=f"Bearer {self.raw_token}")
        self.assertIn(resp.status_code, (401, 403))

    def test_non_edge_scope_token_is_rejected(self):
        # A plain OfflineCapabilityToken WITHOUT the edge scope must not drive the sync POST.
        raw = secrets.token_urlsafe(32)
        device = DeviceRegistration.objects.create(
            school=self.school, user=self.user, device_id="plain-mobile"
        )
        OfflineCapabilityToken.objects.create(
            device=device, school=self.school, user=self.user,
            token_fingerprint=hashlib.sha256(raw.encode()).hexdigest(),
            permission_bitmap=[],  # no EDGE_SYNC_SCOPE
            expires_at=timezone.now() + timedelta(days=1),
        )
        resp = self._post(self._bundle(), auth=f"Bearer {raw}")
        self.assertIn(resp.status_code, (401, 403))
