"""Edge outbox producer -> operator receiver round-trip (Tier 3 Slice 2).

Proves export_edge_delta_bundle captures a tenant's changed records into a signed
delta bundle, and that feeding that bundle to the Slice-1 receiver actually writes
the edge's values onto a stale operator copy (the edge->operator data path, minus
the authenticated network hop which is Slice 3). Also proves the cursor excludes
unchanged records and that an unknown entity is rejected.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.academics.models import AcademicYear, Classroom, Department
from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleUploadView
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership

_SIGN_KEY = "edge-producer-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class EdgeDeltaBundleProducerTests(TestCase):
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
        self.tmp = Path(tempfile.mkdtemp())

    def _post_bundle(self, body_bytes):
        request = self.rf.post(
            "/api/v1/sync/bundle/upload/",
            data=body_bytes,
            content_type="application/x-rmc-sync-bundle+ndjson",
        )
        request.school = self.school
        force_authenticate(request, user=self.user)
        return SyncBundleUploadView.as_view()(request)

    def test_producer_bundle_applies_edge_changes_to_stale_operator_copy(self):
        # 1. Edge state: the records now hold the NEW values.
        self.student.first_name = "EdgeName"
        self.student.save(update_fields=["first_name", "updated_at"])
        self.classroom.name = "EdgeRoom"
        self.classroom.save(update_fields=["name", "updated_at"])
        cursor = (timezone.now() - timezone.timedelta(hours=1)).isoformat()

        # 2. Producer packages everything changed since the cursor.
        out_path = self.tmp / "edge.rmcdelta"
        call_command("export_edge_delta_bundle", slug=self.school.slug, since=cursor, out=str(out_path))
        bundle = out_path.read_bytes()
        self.assertTrue(bundle)

        # 3. Rewind the "operator" copy to a STALE state (older updated_at) so the
        #    apply is a real write, not a no-op. update() bypasses auto_now.
        old = timezone.now() - timezone.timedelta(days=1)
        StudentProfile.objects.filter(pk=self.student.pk).update(first_name="StaleName", updated_at=old)
        Classroom.objects.filter(pk=self.classroom.pk).update(name="StaleRoom", updated_at=old)

        # 4. Apply through the Slice-1 receiver.
        resp = self._post_bundle(bundle)
        self.assertEqual(resp.status_code, 200, getattr(resp, "data", None))
        self.assertTrue(resp.data["ok"])
        self.assertGreaterEqual(resp.data["applied"], 2)
        self.assertEqual(resp.data["conflicts"], 0)

        self.student.refresh_from_db()
        self.classroom.refresh_from_db()
        self.assertEqual(self.student.first_name, "EdgeName")
        self.assertEqual(self.classroom.name, "EdgeRoom")

    def test_cursor_excludes_unchanged_records(self):
        # Force both records to be OLD, then ask for changes since "now".
        old = timezone.now() - timezone.timedelta(days=2)
        StudentProfile.objects.filter(pk=self.student.pk).update(updated_at=old)
        Classroom.objects.filter(pk=self.classroom.pk).update(updated_at=old)
        future_cursor = timezone.now().isoformat()

        out_path = self.tmp / "empty.rmcdelta"
        call_command("export_edge_delta_bundle", slug=self.school.slug, since=future_cursor, out=str(out_path))
        resp = self._post_bundle(out_path.read_bytes())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["received"], 0)
        self.assertEqual(resp.data["applied"], 0)

    def test_unknown_entity_is_rejected(self):
        out_path = self.tmp / "x.rmcdelta"
        with self.assertRaises(CommandError):
            call_command(
                "export_edge_delta_bundle",
                slug=self.school.slug,
                entities="wizardry",
                out=str(out_path),
            )
