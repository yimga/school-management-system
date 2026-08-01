"""Signed sync-bundle upload receiver — verifies then PERSISTS via the delta path.

Tier 3 Slice 1: SyncBundleUploadView used to verify a signed bundle and return a
row count WITHOUT writing anything. These tests prove it now applies the rows
through the same apply_changes path DeltaSyncAPI uses (real persistence + the
updated_at conflict check), and that the UUID school-id binding actually works
(the old int() comparison would have 500'd on a real School.pk).
"""

from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleUploadView
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import SyncConflict
from apps.sync_engine.delta_bundle import export_delta_bundle

_SIGN_KEY = "sync-bundle-upload-test-key"


def _bundle_for(school_id, rows, device_id="edge-box-1"):
    return export_delta_bundle(school_id=str(school_id), rows=rows, device_id=device_id)


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class SyncBundleUploadPersistTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Bundle {uid}",
            slug=f"bundle-{uid}",
            subdomain=f"bundle{uid}",
            is_active=True,
        )
        self.user = User.objects.create_superuser(
            username=f"bundle_admin_{uid}",
            password="Test1234",
            email=f"b{uid}@test.com",
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Njoya",
            date_of_birth="2012-01-01",
        )
        self.rf = APIRequestFactory()

    def _post(self, body_bytes, user=None, school="__default__"):
        request = self.rf.post(
            "/api/v1/sync/bundle/upload/",
            data=body_bytes,
            content_type="application/x-rmc-sync-bundle+ndjson",
        )
        if school == "__default__":
            request.school = self.school
        elif school is not None:
            request.school = school
        force_authenticate(request, user=user or self.user)
        return SyncBundleUploadView.as_view()(request)

    def test_uuid_school_bundle_round_trips_and_persists(self):
        future = (timezone.now() + timezone.timedelta(minutes=10)).isoformat()
        bundle = _bundle_for(
            self.school.id,
            [
                {
                    "entity_type": "student",
                    "id": self.student.pk,
                    "changes": {"first_name": "Renamed"},
                    "updated_at": future,
                }
            ],
        )
        resp = self._post(bundle)
        self.assertEqual(resp.status_code, 200, getattr(resp, "data", None))
        self.assertTrue(resp.data["ok"])
        self.assertEqual(resp.data["received"], 1)
        self.assertEqual(resp.data["applied"], 1)
        self.assertEqual(resp.data["conflicts"], 0)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Renamed")  # actually written

    def test_tampered_signature_rejected(self):
        future = (timezone.now() + timezone.timedelta(minutes=10)).isoformat()
        bundle = _bundle_for(
            self.school.id,
            [
                {
                    "entity_type": "student",
                    "id": self.student.pk,
                    "changes": {"first_name": "Original"},
                    "updated_at": future,
                }
            ],
        )
        tampered = bundle.replace(b"Original", b"Tampered", 1)  # payload no longer matches HMAC
        resp = self._post(tampered)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("signature_mismatch", resp.data["errors"])
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Ada")  # nothing written

    def test_school_mismatch_rejected(self):
        other_school_id = uuid.uuid4()
        bundle = _bundle_for(
            other_school_id,
            [
                {
                    "entity_type": "student",
                    "id": self.student.pk,
                    "changes": {"first_name": "Nope"},
                    "updated_at": timezone.now().isoformat(),
                }
            ],
        )
        resp = self._post(bundle)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("school_mismatch", resp.data["errors"])
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Ada")

    def test_conflict_is_recorded_not_applied(self):
        # Make the server record newer than the client's edit.
        self.student.first_name = "ServerName"
        self.student.save(update_fields=["first_name", "updated_at"])
        self.student.refresh_from_db()
        server_dt = self.student.updated_at
        if timezone.is_naive(server_dt):
            server_dt = timezone.make_aware(server_dt, timezone.get_current_timezone())
        stale = (server_dt - timezone.timedelta(minutes=5)).isoformat()
        bundle = _bundle_for(
            self.school.id,
            [
                {
                    "entity_type": "student",
                    "id": self.student.pk,
                    "changes": {"first_name": "ClientName"},
                    "updated_at": stale,
                }
            ],
        )
        resp = self._post(bundle)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["applied"], 0)
        self.assertEqual(resp.data["conflicts"], 1)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "ServerName")  # not overwritten
        self.assertEqual(SyncConflict.objects.filter(school=self.school).count(), 1)

    def test_no_tenant_context_is_forbidden(self):
        resp = self._post(b"", school=None)
        self.assertEqual(resp.status_code, 403)
