"""Cloud->box delta PULL + echo-suppression (Phase 2 of the bidirectional edge sync).

Proves the missing downstream half of the edge loop:
  * the download endpoint serves a signed delta bundle of the tenant's changes, honours
    the ``since`` cursor, and stamps the new high-water in the response header;
  * a box applies a pulled bundle through the shared apply path (values land);
  * ECHO-SUPPRESSION: a row written by sync is NOT re-emitted by the reverse delta, yet
    a subsequent genuine LOCAL edit of the same row IS — so bidirectional sync converges
    instead of ping-ponging.
"""
from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.academics.models import AcademicYear, Classroom, Department
from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleDownloadView
from apps.api.sync_services import apply_changes
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import verify_and_parse_bundle
from apps.sync_engine.edge_inbox import apply_pulled_bundle
from apps.sync_engine.edge_outbox import (
    SYNC_HIGH_WATER_HEADER,
    build_edge_delta_bundle,
    mint_edge_credential,
)
from apps.sync_engine.models import SyncApplyLedger

_SIGN_KEY = "edge-pull-test-key"


def _student_rows(bundle_bytes, school_id):
    rows, errors = verify_and_parse_bundle(bundle_bytes, expected_school_id=school_id)
    assert not errors, errors
    return [r for r in rows if r.get("entity_type") == "student"]


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class EdgePullSyncTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Edge {uid}", slug=f"edge-{uid}", subdomain=f"edge{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"edge_admin_{uid}", password="Test1234", email=f"e{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        year = AcademicYear.objects.create(
            name="2024-2025", starts_on="2024-01-01", ends_on="2024-12-31", school=self.school
        )
        dept = Department.objects.create(name=f"Dept {uid}", code=f"D{uid[:4]}")
        self.classroom = Classroom.objects.create(
            academic_year=year, department=dept, name="RoomA", code=f"RA{uid[:4]}", school=self.school
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Njoya", date_of_birth="2012-01-01"
        )
        self.rf = APIRequestFactory()

    # --------------------------------------------------------------------- #
    # Download endpoint
    # --------------------------------------------------------------------- #
    def _download(self, query=""):
        request = self.rf.get(f"/api/v1/sync/bundle/download/{query}")
        request.school = self.school
        force_authenticate(request, user=self.user)
        return SyncBundleDownloadView.as_view()(request)

    def test_download_serves_signed_bundle_with_high_water(self):
        resp = self._download()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("x-rmc-sync-bundle", resp["Content-Type"])
        body = resp.getvalue() if hasattr(resp, "getvalue") else resp.content
        students = _student_rows(body, self.school.id)
        self.assertTrue(any(r["id"] == self.student.pk for r in students))
        # High-water header is set (there is at least one dated row) so the box can
        # advance its pull cursor without re-parsing the body.
        self.assertTrue(resp.get(SYNC_HIGH_WATER_HEADER))

    def test_download_since_cursor_excludes_unchanged(self):
        # Force every row OLD, then ask for changes since "now" -> empty.
        old = timezone.now() - timezone.timedelta(days=2)
        StudentProfile.objects.filter(pk=self.student.pk).update(updated_at=old)
        Classroom.objects.filter(pk=self.classroom.pk).update(updated_at=old)
        future = timezone.now().isoformat().replace("+", "%2B")
        resp = self._download(query=f"?since={future}")
        self.assertEqual(resp.status_code, 200)
        body = resp.getvalue() if hasattr(resp, "getvalue") else resp.content
        self.assertEqual(_student_rows(body, self.school.id), [])

    def test_download_requires_authentication(self):
        # No credential, no forced auth, no school -> not served.
        request = self.rf.get("/api/v1/sync/bundle/download/")
        resp = SyncBundleDownloadView.as_view()(request)
        self.assertIn(resp.status_code, (401, 403))

    def test_download_via_edge_machine_credential(self):
        # Full auth integration: a real edge bearer resolves user+school.
        raw_token, _tok = mint_edge_credential(self.school, self.user, device_id="pull-box")
        request = self.rf.get(
            "/api/v1/sync/bundle/download/", HTTP_AUTHORIZATION=f"Bearer {raw_token}"
        )
        resp = SyncBundleDownloadView.as_view()(request)
        self.assertEqual(resp.status_code, 200, getattr(resp, "data", None))

    # --------------------------------------------------------------------- #
    # Box applies a pulled bundle
    # --------------------------------------------------------------------- #
    def test_pulled_bundle_applies_on_box(self):
        # Bundle captures the CURRENT (fresh) student; rewind the local copy to stale so
        # the apply is a real write, then apply the pulled bundle.
        self.student.first_name = "CloudName"
        self.student.save(update_fields=["first_name", "updated_at"])
        resp = self._download()
        bundle = resp.getvalue() if hasattr(resp, "getvalue") else resp.content

        old = timezone.now() - timezone.timedelta(days=1)
        StudentProfile.objects.filter(pk=self.student.pk).update(first_name="StaleName", updated_at=old)

        result = apply_pulled_bundle(self.school, self.user, bundle, origin="cloud-pull")
        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(result["applied"], 1)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "CloudName")
        # Provenance recorded for echo-suppression.
        self.assertTrue(
            SyncApplyLedger.objects.filter(
                school=self.school, entity_type="student", local_pk=str(self.student.pk)
            ).exists()
        )

    # --------------------------------------------------------------------- #
    # Echo-suppression — the load-bearing bidirectional invariant
    # --------------------------------------------------------------------- #
    def test_sync_applied_row_is_not_echoed_but_local_edit_is(self):
        # 1. Apply a change AS SYNC (cloud-pull) -> bumps updated_at + records the ledger.
        newer = (timezone.now() + timezone.timedelta(seconds=60)).isoformat()
        out = apply_changes(
            str(self.school.id),
            self.user,
            [{"entity_type": "student", "id": self.student.pk,
              "changes": {"first_name": "FromCloud"}, "updated_at": newer}],
            persist_conflicts=True,
            sync_origin="cloud-pull",
        )
        self.assertEqual(out["success_count"], 1, out)

        # 2. Reverse delta must NOT contain the just-applied row (would be a pure echo).
        data, _meta = build_edge_delta_bundle(self.school, since=None, entities=["student"])
        echoed = [r for r in _student_rows(data, self.school.id) if r["id"] == self.student.pk]
        self.assertEqual(echoed, [], "sync-applied row was echoed back — infinite loop risk")

        # 3. A genuine LOCAL edit moves updated_at off the recorded value -> it DOES ship.
        self.student.refresh_from_db()
        self.student.first_name = "LocalEdit"
        self.student.save(update_fields=["first_name", "updated_at"])
        data2, _meta2 = build_edge_delta_bundle(self.school, since=None, entities=["student"])
        shipped = [r for r in _student_rows(data2, self.school.id) if r["id"] == self.student.pk]
        self.assertEqual(len(shipped), 1, "genuine local edit was wrongly suppressed")
        self.assertEqual(shipped[0]["changes"].get("first_name"), "LocalEdit")
