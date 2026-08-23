"""The stale-offline-write guard must actually fire for attendance.

Both attendance writers detect a stale offline write by looking up the existing
row's ``updated_at`` in a map keyed by ``(ids..., date)``.  The records are built
straight from the client's JSON, so their ``date`` is whatever the wire carried --
a string -- while the map is filled from ``values_list("date", ...)``, which the
ORM hands back as ``datetime.date``.  The two keys can never meet, so the guard
silently degraded to "the offline write always wins" and the newer online
correction was overwritten.

These tests drive the real writers against the real tables, so they measure the
end state of the row rather than the shape of a hand-built dict.
"""

from __future__ import annotations

import uuid
from datetime import date as _date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Attendance, Classroom, Department
from apps.accounts.models import User
from apps.people.models import StudentProfile, TeacherAttendance, TeacherProfile
from apps.schools.models import School

_DAY = "2026-06-04"


class WALAttendanceStaleGuardTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"WAL {uid}", slug=f"wal-{uid}", subdomain=f"wal{uid}", is_active=True
        )
        year = AcademicYear.objects.create(
            name="2025-2026",
            starts_on="2026-01-01",
            ends_on="2026-12-31",
            school=self.school,
        )
        dept = Department.objects.create(name=f"Dept {uid}", code=f"D{uid[:4]}")
        self.classroom = Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="RoomA",
            code=f"RA{uid[:4]}",
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Njoya",
            date_of_birth="2012-01-01",
        )

    def _envelope(self, *, captured_at, status="absent"):
        return {
            "domain": "attendance",
            "txn_id": uuid.uuid4().hex,
            "tenant_hash": "abc123abc123",
            "school_id": self.school.pk,
            "captured_at": captured_at,
            "actions": [
                {
                    "student_id": self.student.pk,
                    "classroom_id": self.classroom.pk,
                    "date": _DAY,
                    "status": status,
                }
            ],
        }

    def _online_correction(self):
        """The office's 09:00 correction, already durable when the box reconnects."""
        return Attendance.objects.create(
            school=self.school,
            student=self.student,
            classroom=self.classroom,
            date=_DAY,
            status="excused",
        )

    def test_stale_offline_write_does_not_clobber_newer_online_correction(self):
        from apps.wal_stream import writers

        row = self._online_correction()
        # Captured an hour BEFORE the online correction that is already in the table.
        captured_at = (row.updated_at - timedelta(hours=1)).timestamp()

        with patch("apps.wal_stream.tasks.record_wal_conflicts") as conflicts:
            writers._apply_attendance(self._envelope(captured_at=captured_at))

        row.refresh_from_db()
        self.assertEqual(row.status, "excused")
        # Not vacuous: the writer reached the conflict branch and reported the
        # refused row rather than, say, dropping the action earlier for a bad FK.
        self.assertTrue(conflicts.called)

    def test_fresh_offline_write_still_lands(self):
        """Guard against the previous test passing for the wrong reason.

        If the writer never reached the table at all (unresolved session,
        cross-tenant drop, missing school) the stale assertion above would pass
        against a completely broken writer.  The same envelope with a LATER
        capture time must write.
        """
        from apps.wal_stream import writers

        row = self._online_correction()
        captured_at = (row.updated_at + timedelta(hours=1)).timestamp()

        writers._apply_attendance(self._envelope(captured_at=captured_at))

        row.refresh_from_db()
        self.assertEqual(row.status, "absent")

    def test_session_id_marker_date_is_also_normalised(self):
        """The compact marker path feeds the same freshness key."""
        from apps.wal_stream import writers

        row = self._online_correction()
        envelope = self._envelope(
            captured_at=(row.updated_at - timedelta(hours=1)).timestamp()
        )
        envelope["actions"] = [
            {
                "student_id": self.student.pk,
                "session_id": "{0}::{1}".format(self.classroom.pk, _DAY),
                "status": "absent",
            }
        ]

        with patch("apps.wal_stream.tasks.record_wal_conflicts") as conflicts:
            writers._apply_attendance(envelope)

        row.refresh_from_db()
        self.assertEqual(row.status, "excused")
        self.assertTrue(conflicts.called)

    def test_stored_date_is_a_real_date_object(self):
        """A fresh offline write must persist a date, not the client's string.

        The row is re-read through the ORM, so this pins what actually reached the
        column rather than what the instance happened to hold in memory.
        """
        from apps.wal_stream import writers

        writers._apply_attendance(
            self._envelope(captured_at=timezone.now().timestamp())
        )
        stored = Attendance.objects.get(
            student=self.student, classroom=self.classroom
        )
        self.assertEqual(stored.date, _date(2026, 6, 4))

    def test_unparseable_date_is_dropped_not_raised(self):
        """A corrupted client row must not take the whole envelope down.

        The drainer's bounded-retry handler does not catch ValidationError, so a
        date that only fails at ``get_prep_value`` time would wedge the tenant's
        drain forever.  The writer refuses it per-action instead.
        """
        from apps.wal_stream import writers

        envelope = self._envelope(captured_at=timezone.now().timestamp())
        envelope["actions"] = [
            {
                "student_id": self.student.pk,
                "session_id": "{0}::not-a-date".format(self.classroom.pk),
                "status": "present",
            }
        ]

        writers._apply_attendance(envelope)  # must not raise

        self.assertEqual(Attendance.objects.filter(student=self.student).count(), 0)


class WALTeacherAttendanceStaleGuardTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="WALT {0}".format(uid),
            slug="walt-{0}".format(uid),
            subdomain="walt{0}".format(uid),
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="t{0}".format(uid),
            password="Test1234",
            email="t{0}@test.com".format(uid),
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.user, school=self.school, staff_id="S{0}".format(uid[:4])
        )

    def _envelope(self, *, captured_at, status="ABSENT"):
        return {
            "domain": "teacher_attendance",
            "txn_id": uuid.uuid4().hex,
            "tenant_hash": "abc123abc123",
            "school_id": self.school.pk,
            "captured_at": captured_at,
            "actions": [
                {"teacher_id": self.teacher.pk, "date": _DAY, "status": status}
            ],
        }

    def test_stale_offline_write_does_not_clobber_newer_online_correction(self):
        from apps.wal_stream import writers

        row = TeacherAttendance.objects.create(
            teacher=self.teacher, date=_DAY, status="ON_LEAVE"
        )
        captured_at = (row.updated_at - timedelta(hours=1)).timestamp()

        with patch("apps.wal_stream.tasks.record_wal_conflicts") as conflicts:
            writers._apply_teacher_attendance(self._envelope(captured_at=captured_at))

        row.refresh_from_db()
        self.assertEqual(row.status, "ON_LEAVE")
        self.assertTrue(conflicts.called)

    def test_fresh_offline_write_still_lands(self):
        from apps.wal_stream import writers

        row = TeacherAttendance.objects.create(
            teacher=self.teacher, date=_DAY, status="ON_LEAVE"
        )
        captured_at = (row.updated_at + timedelta(hours=1)).timestamp()

        writers._apply_teacher_attendance(self._envelope(captured_at=captured_at))

        row.refresh_from_db()
        self.assertEqual(row.status, "ABSENT")

    def test_unparseable_date_is_dropped_not_raised(self):
        from apps.wal_stream import writers

        envelope = self._envelope(captured_at=timezone.now().timestamp())
        envelope["actions"] = [
            {"teacher_id": self.teacher.pk, "date": "2026-13-45", "status": "PRESENT"}
        ]

        writers._apply_teacher_attendance(envelope)  # must not raise

        self.assertEqual(
            TeacherAttendance.objects.filter(teacher=self.teacher).count(), 0
        )


class WALAttendanceWireShapeTests(TestCase):
    """The exact payload the shipped client sends must actually land.

    ``static/js/_pages/rmc-attendance-wal-enhance.js`` harvests ids out of an input
    name with a regex, so ``student_id``/``teacher_id`` cross the wire as STRINGS,
    and the compact ``session_id`` marker is parsed out of a string too.  The
    cross-tenant ownership check compares those against pks read back from the DB,
    which are ints -- ``"7" in {7}`` is False -- so every row the real UI produced
    was discarded as "cross tenant" and logged as such.  Nothing above this catches
    it: the envelope was applied, the drain reported success, and the table stayed
    empty.
    """

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="Wire {0}".format(uid),
            slug="wire-{0}".format(uid),
            subdomain="wire{0}".format(uid),
            is_active=True,
        )
        year = AcademicYear.objects.create(
            name="2025-2026",
            starts_on="2026-01-01",
            ends_on="2026-12-31",
            school=self.school,
        )
        dept = Department.objects.create(name="Dept {0}".format(uid), code="W{0}".format(uid[:4]))
        self.classroom = Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="RoomW",
            code="RW{0}".format(uid[:4]),
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Njoya",
            date_of_birth="2012-01-01",
        )

    def test_string_ids_from_the_browser_are_not_dropped_as_cross_tenant(self):
        from apps.wal_stream import writers

        writers._apply_attendance(
            {
                "domain": "attendance",
                "txn_id": uuid.uuid4().hex,
                "tenant_hash": "abc123abc123",
                "school_id": self.school.pk,
                "captured_at": timezone.now().timestamp(),
                "actions": [
                    {
                        "student_id": str(self.student.pk),
                        "session_id": "{0}::{1}".format(self.classroom.pk, _DAY),
                        "status": "absent",
                        "marked_at": "2026-06-04T08:00:00.000Z",
                    }
                ],
            }
        )

        stored = Attendance.objects.get(student=self.student, classroom=self.classroom)
        self.assertEqual(stored.status, "absent")
        self.assertEqual(stored.date, _date(2026, 6, 4))
        self.assertEqual(stored.school_id, self.school.pk)

    def test_string_teacher_id_from_the_browser_is_not_dropped(self):
        from apps.wal_stream import writers

        user = User.objects.create_user(
            username="wire-teacher-{0}".format(uuid.uuid4().hex[:6]),
            password="Test1234",
        )
        teacher = TeacherProfile.objects.create(user=user, school=self.school)

        writers._apply_teacher_attendance(
            {
                "domain": "teacher_attendance",
                "txn_id": uuid.uuid4().hex,
                "tenant_hash": "abc123abc123",
                "school_id": self.school.pk,
                "captured_at": timezone.now().timestamp(),
                "actions": [
                    {"teacher_id": str(teacher.pk), "date": _DAY, "status": "ABSENT"}
                ],
            }
        )

        stored = TeacherAttendance.objects.get(teacher=teacher)
        self.assertEqual(stored.status, "ABSENT")
        self.assertEqual(stored.date, _date(2026, 6, 4))
