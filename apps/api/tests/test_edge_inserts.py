"""Edge INSERTS — upsert offline-created rows by client_offline_id (Tier 3 Slice 4/5).

Records created offline on the box carry a client_offline_id and the box's local pk
(meaningless on the operator). The receiver upserts them by (school, client_offline_id),
never by pk, so a box-local pk can't collide with a different operator record.

Slice 5 (the honest residual): a FK pointing at ANOTHER new row in the same bundle is
REMAPPED onto the referent's freshly-assigned operator pk (rows are applied in dependency
order). If the referent couldn't be created, the FK is dropped so it can't mis-link — a
required FK then fails cleanly and is reported.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.academics.models import AcademicYear, Attendance, Classroom, Department
from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleUploadView
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import export_delta_bundle

_SIGN_KEY = "edge-insert-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class EdgeInsertReceiverTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Ins {uid}", slug=f"ins-{uid}", subdomain=f"ins{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"ins_admin_{uid}", password="Test1234", email=f"i{uid}@test.com"
        )
        SchoolMembership.objects.create(user=self.user, school=self.school, role="ADMIN", is_primary=True)
        year = AcademicYear.objects.create(
            name="2024-2025", starts_on="2024-01-01", ends_on="2024-12-31", school=self.school
        )
        dept = Department.objects.create(name=f"Dept {uid}", code=f"D{uid[:4]}")
        self.classroom = Classroom.objects.create(  # a CLONED classroom (client_offline_id="")
            academic_year=year, department=dept, name="RoomA", code=f"RA{uid[:4]}", school=self.school
        )
        self.cloned_student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Njoya", date_of_birth="2012-01-01"
        )
        self.rf = APIRequestFactory()
        self.future = (timezone.now() + timedelta(minutes=10)).isoformat()

    def _post(self, rows):
        bundle = export_delta_bundle(school_id=str(self.school.id), rows=rows, device_id="box")
        request = self.rf.post(
            "/api/v1/sync/bundle/upload/", data=bundle,
            content_type="application/x-rmc-sync-bundle+ndjson",
        )
        request.school = self.school
        force_authenticate(request, user=self.user)
        return SyncBundleUploadView.as_view()(request)

    def test_new_student_created_by_client_offline_id(self):
        coid = "box-stu-001"
        resp = self._post([{
            "entity_type": "student", "id": 999999, "client_offline_id": coid,
            "changes": {"first_name": "NewKid", "last_name": "Fon"}, "updated_at": self.future,
        }])
        self.assertEqual(resp.status_code, 200, getattr(resp, "data", None))
        self.assertEqual(resp.data["created"], 1)
        created = StudentProfile.objects.get(school=self.school, client_offline_id=coid)
        self.assertEqual(created.first_name, "NewKid")
        self.assertNotEqual(created.pk, 999999)  # operator assigned its OWN pk, not the box's

    def test_reinsert_is_idempotent(self):
        coid = "box-stu-002"
        row = {"entity_type": "student", "id": 999998, "client_offline_id": coid,
               "changes": {"first_name": "Bee", "last_name": "Cee"}, "updated_at": self.future}
        self._post([row])
        resp = self._post([row])  # second time: upsert, no duplicate
        self.assertEqual(resp.data["created"], 0)
        self.assertEqual(resp.data["upserted"], 1)
        self.assertEqual(StudentProfile.objects.filter(school=self.school, client_offline_id=coid).count(), 1)

    def test_cloned_record_update_still_works(self):
        resp = self._post([{
            "entity_type": "student", "id": self.cloned_student.pk, "client_offline_id": "",
            "changes": {"first_name": "EditedClone"}, "updated_at": self.future,
        }])
        self.assertEqual(resp.data["applied"], 1)
        self.assertEqual(resp.data["created"], 0)
        self.cloned_student.refresh_from_db()
        self.assertEqual(self.cloned_student.first_name, "EditedClone")

    def test_missing_pk_without_coid_is_not_inserted(self):
        resp = self._post([{
            "entity_type": "student", "id": 888888, "client_offline_id": "",
            "changes": {"first_name": "Ghost"}, "updated_at": self.future,
        }])
        self.assertEqual(resp.data["created"], 0)
        self.assertEqual(resp.data["applied"], 0)
        self.assertTrue(any(r["status"] == 404 for r in resp.data["results"]))
        self.assertFalse(StudentProfile.objects.filter(first_name="Ghost").exists())

    def test_attendance_insert_for_cloned_student_created(self):
        coid = "box-att-001"
        resp = self._post([{
            "entity_type": "attendance", "id": 777777, "client_offline_id": coid,
            "changes": {"student_id": self.cloned_student.pk, "classroom_id": self.classroom.pk,
                        "date": "2026-05-01", "status": "present"},
            "updated_at": self.future,
        }])
        self.assertEqual(resp.data["created"], 1, resp.data)
        att = Attendance.objects.get(school=self.school, client_offline_id=coid)
        self.assertEqual(att.student_id, self.cloned_student.pk)

    def test_attendance_for_new_student_now_remapped_and_created(self):
        """Slice 5 residual: attendance for a brand-new student (both offline-created in
        the SAME bundle) is remapped onto the student's freshly-assigned operator pk —
        no longer dropped. Both rows land; the FK points at the real operator pk."""
        new_student_local_pk = 919191
        rows = [
            {"entity_type": "student", "id": new_student_local_pk, "client_offline_id": "box-stu-x",
             "changes": {"first_name": "New", "last_name": "Student"}, "updated_at": self.future},
            {"entity_type": "attendance", "id": 929292, "client_offline_id": "box-att-x",
             "changes": {"student_id": new_student_local_pk, "classroom_id": self.classroom.pk,
                         "date": "2026-05-02", "status": "present"}, "updated_at": self.future},
        ]
        resp = self._post(rows)
        self.assertEqual(resp.data["created"], 2, resp.data)
        new_student = StudentProfile.objects.get(school=self.school, client_offline_id="box-stu-x")
        att = Attendance.objects.get(school=self.school, client_offline_id="box-att-x")
        self.assertEqual(att.student_id, new_student.pk)          # remapped to the operator pk
        self.assertNotEqual(att.student_id, new_student_local_pk)  # NOT the box's local pk

    def test_attendance_before_student_in_bundle_still_remapped(self):
        """Dependency order — not bundle order — governs: attendance listed BEFORE its
        new student still resolves (the student is created first internally), and results
        come back in the original bundle order."""
        slp = 800001
        rows = [
            {"entity_type": "attendance", "id": 800002, "client_offline_id": "box-att-y",
             "changes": {"student_id": slp, "classroom_id": self.classroom.pk,
                         "date": "2026-05-03", "status": "present"}, "updated_at": self.future},
            {"entity_type": "student", "id": slp, "client_offline_id": "box-stu-y",
             "changes": {"first_name": "Yin", "last_name": "Yang"}, "updated_at": self.future},
        ]
        resp = self._post(rows)
        self.assertEqual(resp.data["created"], 2, resp.data)
        new_student = StudentProfile.objects.get(school=self.school, client_offline_id="box-stu-y")
        att = Attendance.objects.get(school=self.school, client_offline_id="box-att-y")
        self.assertEqual(att.student_id, new_student.pk)
        # results preserve the ORIGINAL bundle order (attendance idx 0, student idx 1)
        self.assertEqual([r["index"] for r in resp.data["insert_results"]], [0, 1])

    def test_dependent_fk_dropped_when_referent_cannot_be_created(self):
        """Fail-clean fallback: a new Classroom can't be created via the sync field set
        (needs department + a unique code), so a new student referencing it has its
        classroom_id dropped — the student still lands, never mis-linked to the box pk,
        and the dropped link is REPORTED (dropped_fks) rather than silently orphaned."""
        new_cls_local_pk = 700001
        rows = [
            {"entity_type": "classroom", "id": new_cls_local_pk, "client_offline_id": "box-cls-y",
             "changes": {"name": "GhostRoom"}, "updated_at": self.future},
            {"entity_type": "student", "id": 700002, "client_offline_id": "box-stu-z",
             "changes": {"first_name": "Zed", "last_name": "Zee", "classroom_id": new_cls_local_pk},
             "updated_at": self.future},
        ]
        resp = self._post(rows)
        self.assertFalse(Classroom.objects.filter(school=self.school, client_offline_id="box-cls-y").exists())
        student = StudentProfile.objects.get(school=self.school, client_offline_id="box-stu-z")
        self.assertIsNone(student.classroom_id)  # FK to the uncreatable classroom dropped
        self.assertTrue(any(r["status"] == 422 for r in resp.data["insert_results"]))
        # The student's dropped classroom link is surfaced, not silently swallowed.
        stu_result = next(r for r in resp.data["insert_results"] if r["data"].get("id") == student.pk)
        self.assertIn("classroom_id", stu_result["data"].get("dropped_fks", []))

    def test_classroom_update_with_phantom_is_active_does_not_crash(self):
        """`is_active` is not a Classroom field; it was removed from the allow-list so a
        classroom UPDATE carrying it no longer crashes (`save(update_fields=['is_active'])`
        -> FieldError). The real field still applies; the phantom is ignored."""
        resp = self._post([{
            "entity_type": "classroom", "id": self.classroom.pk, "client_offline_id": "",
            "changes": {"name": "Renamed Room", "is_active": False}, "updated_at": self.future,
        }])
        self.assertEqual(resp.data["applied"], 1, resp.data)
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.name, "Renamed Room")

    def test_dataerror_is_isolated_not_a_500(self):
        """A per-row DataError (value too long / out of range on Postgres — a
        DatabaseError sibling of IntegrityError) must be caught so the per-row savepoint
        never escapes and rolls back the batch. SQLite doesn't enforce max_length, so we
        force the DataError to exercise the except path."""
        from unittest.mock import patch

        from django.db import DataError

        with patch("apps.people.models.StudentProfile.objects.get_or_create",
                   side_effect=DataError("value too long for type character varying(20)")):
            resp = self._post([{
                "entity_type": "student", "id": 500001, "client_offline_id": "box-de-1",
                "changes": {"first_name": "X"}, "updated_at": self.future,
            }])
        self.assertEqual(resp.status_code, 200)  # batch survived; no uncaught 500
        self.assertEqual(resp.data["created"], 0)
        self.assertTrue(any(r["status"] == 422 for r in resp.data["insert_results"]))

    def test_malformed_non_dict_bundle_row_does_not_500(self):
        """A signed bundle line that is a JSON scalar/array (not an object) must be
        dropped to a `malformed` count, not AttributeError-500 the whole upload."""
        rows = [
            42,  # malformed
            {"entity_type": "student", "id": 500002, "client_offline_id": "box-ok-1",
             "changes": {"first_name": "Fine"}, "updated_at": self.future},
        ]
        resp = self._post(rows)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["malformed"], 1)
        self.assertEqual(resp.data["created"], 1)  # the valid row still landed
        self.assertTrue(StudentProfile.objects.filter(school=self.school, client_offline_id="box-ok-1").exists())

    def test_classroom_insert_missing_required_fields_fails_cleanly(self):
        coid = "box-cls-001"
        resp = self._post([{
            "entity_type": "classroom", "id": 666666, "client_offline_id": coid,
            "changes": {"name": "OfflineRoom", "is_active": True}, "updated_at": self.future,
        }])
        # Classroom needs department + a unique code (not in the sync field set) -> IntegrityError
        # -> reported 422, not created, batch survives.
        self.assertFalse(Classroom.objects.filter(school=self.school, client_offline_id=coid).exists())
        self.assertTrue(any(r["status"] == 422 for r in resp.data["insert_results"]))
