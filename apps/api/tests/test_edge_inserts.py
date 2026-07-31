"""Edge INSERTS — upsert offline-created rows by client_offline_id (Tier 3 Slice 4).

Records created offline on the box carry a client_offline_id and the box's local pk
(meaningless on the operator). The receiver upserts them by (school, client_offline_id),
never by pk, so a box-local pk can't collide with a different operator record; a FK
pointing at another new row's local pk is dropped so it can't mis-link.
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

    def test_attendance_for_new_student_fails_cleanly_no_corruption(self):
        new_student_local_pk = 919191
        rows = [
            {"entity_type": "student", "id": new_student_local_pk, "client_offline_id": "box-stu-x",
             "changes": {"first_name": "New", "last_name": "Student"}, "updated_at": self.future},
            {"entity_type": "attendance", "id": 929292, "client_offline_id": "box-att-x",
             "changes": {"student_id": new_student_local_pk, "classroom_id": self.classroom.pk,
                         "date": "2026-05-02", "status": "present"}, "updated_at": self.future},
        ]
        resp = self._post(rows)
        # student created; attendance's FK to the new student is dropped -> required student
        # missing -> row fails cleanly (reported), never mis-linked, batch survives.
        self.assertEqual(resp.data["created"], 1)
        self.assertFalse(Attendance.objects.filter(school=self.school, client_offline_id="box-att-x").exists())
        self.assertTrue(any(r["status"] == 422 for r in resp.data["insert_results"]))

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
