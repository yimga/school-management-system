"""Metric-15 (part B): scheduling <-> booking (#10) room-vs-time cross-check.

Proves that publishing a timetable REFUSES when a scheduled class and a confirmed
ad-hoc room booking would occupy the same linked room at the same wall-clock time,
and publishes normally otherwise (non-overlapping booking / unlinked room).

Two layers:
  * SQLite-provable (runs on every backend): the publish gate expands each linked
    entry's weekly slot across the term and refuses on overlap with a CONFIRMED
    ``ResourceBooking``; a non-overlapping booking and an unlinked room publish.
  * ``@requires_postgres`` (django-tests-postgres.yml): the btree_gist
    ``ExclusionConstraint`` itself blocks a second overlapping confirmed booking on
    the linked resource (raises ``IntegrityError``).

BACKEND NOTE — ``schoolops.ResourceBooking.time_range`` is a Postgres
``DateTimeRangeField``. Its ORM write path (``get_placeholder`` -> ``%s::tstzrange``)
cannot run on SQLite, and the column has no ``from_db_value`` so it round-trips as
the canonical text ``'[lower,upper)'``. ``create_resource_booking`` therefore only
works on Postgres. To keep the cross-check itself SQLite-provable with a REAL
confirmed row, ``_confirmed_booking`` raw-inserts that exact canonical text on
SQLite (byte-identical to what Postgres stores) and uses the real service on
Postgres. Both land a genuine confirmed ``ResourceBooking`` that the production
cross-check reads through the same backend-aware ``_booking_bounds`` path.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, override_settings, tag
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Subject,
    Term,
)
from apps.academics.scheduling import (
    Room,
    Schedule,
    ScheduleEntry,
    TimeSlot,
    _slot_occurrences,
    find_schedule_booking_conflicts,
)
from apps.accounts.models import Permission, User
from apps.schoolops.booking_services import create_resource_booking
from apps.schoolops.models import BookableResource, ResourceBooking
from apps.schools.models import School, SchoolMembership

_HOST = "ttbook.runmycampus.com"
_TENANT_URLCONF = "config.tenant_urls"

requires_postgres = unittest.skipUnless(
    connection.vendor == "postgresql",
    "ResourceBooking.time_range (DateTimeRangeField + gist exclusion) is Postgres-only",
)

_TERM_START = date(2025, 9, 1)
_TERM_END = date(2025, 12, 15)
_SLOT_DAY = 0  # Monday (matches TimeSlot / date.weekday())
_SLOT_START = time(8, 0)
_SLOT_END = time(9, 0)


def _aware(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


class _BookingScenarioMixin:
    """Builds a one-class schedule whose room is (optionally) linked to a resource."""

    def _scenario(self, *, link_room=True):
        uid = uuid.uuid4().hex[:8]
        year = AcademicYear.objects.create(
            school=self.school,
            name=f"2025/2026-{uid}",
            start_date=_TERM_START,
            end_date=_TERM_END,
            is_active=True,
        )
        term = Term.objects.create(
            school=self.school,
            academic_year=year,
            name="Term 1",
            position=1,
            start_date=_TERM_START,
            end_date=_TERM_END,
            is_active=True,
        )
        dept = Department.objects.create(
            school=self.school, name=f"Dept-{uid}", code=f"D{uid}"
        )
        classroom = Classroom.objects.create(
            school=self.school,
            academic_year=year,
            department=dept,
            name=f"Form-{uid}",
            code=f"F-{uid}",
        )
        subject = Subject.objects.create(school=self.school, name=f"Math-{uid}")
        teacher = User.objects.create_user(
            username=f"t_{uid}", password="Test1234", role=User.Role.TEACHER
        )
        resource = BookableResource.objects.create(
            school=self.school, name=f"Lab-{uid}", capacity=1
        )
        room = Room.objects.create(
            name=f"Room-{uid}",
            room_type="CLASSROOM",
            capacity=40,
            bookable_resource=resource if link_room else None,
        )
        slot, _ = TimeSlot.objects.get_or_create(
            day_of_week=_SLOT_DAY,
            start_time=_SLOT_START,
            end_time=_SLOT_END,
            defaults={"slot_name": "P8", "is_active": True},
        )
        schedule = Schedule.objects.create(
            name=f"Sched-{uid}",
            academic_year=year,
            term=term,
            status="DRAFT",
            created_by=teacher,
        )
        entry = ScheduleEntry.objects.create(
            schedule=schedule,
            classroom=classroom,
            subject=subject,
            teacher=teacher,
            room=room,
            time_slot=slot,
        )
        return SimpleNamespace(
            uid=uid,
            year=year,
            term=term,
            classroom=classroom,
            subject=subject,
            teacher=teacher,
            resource=resource,
            room=room,
            slot=slot,
            schedule=schedule,
            entry=entry,
        )

    def _first_occurrence(self):
        """(start, end) datetimes of the first weekly occurrence of the slot."""
        first = list(
            _slot_occurrences(_TERM_START, _TERM_END, _SLOT_DAY, _SLOT_START, _SLOT_END)
        )[0]
        return first  # (naive start, naive end)

    def _confirmed_booking(self, *, resource, start, end, title):
        """Persist a genuine CONFIRMED ResourceBooking on either backend.

        Postgres: the real service. SQLite: raw-insert the canonical range text the
        field round-trips as (the ORM write path is Postgres-only) — the production
        cross-check reads it through the same ``_booking_bounds`` seam.
        """
        start, end = _aware(start), _aware(end)
        if connection.vendor == "postgresql":
            return create_resource_booking(
                school=self.school,
                resource=resource,
                booked_by=None,
                title=title,
                start=start,
                end=end,
            )
        time_range = f"[{start.isoformat()},{end.isoformat()})"
        now = timezone.now().isoformat()
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO schoolops_resourcebooking "
                "(school_id, resource_id, title, time_range, status, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                [self.school.id.hex, resource.id, title, time_range, "confirmed", now, now],
            )
        return ResourceBooking.objects.filter(
            school=self.school, resource=resource, title=title
        ).latest("id")


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _HOST])
class TimetableBookingCrossCheckTests(_BookingScenarioMixin, TestCase):
    """Publish-time room-vs-booking cross-check (SQLite-provable, runs everywhere)."""

    def setUp(self):
        self.uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="TT Booking School",
            slug="ttbook",
            subdomain="ttbook",
            is_active=True,
        )
        self.admin = self._admin()

    def _admin(self):
        user = User.objects.create_user(
            username=f"bk_admin_{uuid.uuid4().hex[:6]}",
            password="Test1234",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=user, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        # Ensure the gate permission exists and is granted (belt-and-suspenders;
        # the ADMIN tier already passes require_permission).
        perm, _ = Permission.objects.get_or_create(
            code="grades.manage", defaults={"name": "Grade & exam management"}
        )
        user.feature_permissions.add(perm)
        return user

    def _client(self):
        c = Client(HTTP_HOST=_HOST)
        c.force_login(self.admin)
        session = c.session
        session["mfa_verified"] = True
        session.save()
        return c

    def _url(self, name, **kwargs):
        return reverse(name, kwargs=kwargs, urlconf=_TENANT_URLCONF)

    # -- refuse on overlap -------------------------------------------------

    def test_publish_refused_when_class_overlaps_confirmed_booking(self):
        sc = self._scenario(link_room=True)
        occ_start, occ_end = self._first_occurrence()
        # Booking 08:30-09:30 overlaps the 08:00-09:00 class occurrence.
        self._confirmed_booking(
            resource=sc.resource,
            start=occ_start + timedelta(minutes=30),
            end=occ_end + timedelta(minutes=30),
            title="Staff meeting",
        )

        # The cross-check surfaces the conflict naming the room + booking.
        conflicts = find_schedule_booking_conflicts(sc.schedule)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["room"], sc.room.name)
        self.assertEqual(conflicts[0]["booking_title"], "Staff meeting")

        resp = self._client().post(
            self._url("academics:timetable_publish", schedule_id=sc.schedule.id)
        )
        self.assertEqual(resp.status_code, 302)
        sc.schedule.refresh_from_db()
        self.assertEqual(sc.schedule.status, "DRAFT", "publish must be refused on booking clash")
        self.assertIsNone(sc.schedule.published_at)

    # -- publish when no overlap ------------------------------------------

    def test_publish_succeeds_when_booking_does_not_overlap(self):
        sc = self._scenario(link_room=True)
        occ_start, occ_end = self._first_occurrence()
        # Booking 10:00-11:00 — no class occurrence there.
        self._confirmed_booking(
            resource=sc.resource,
            start=occ_start + timedelta(hours=2),
            end=occ_end + timedelta(hours=2),
            title="Evening rehearsal",
        )
        self.assertEqual(find_schedule_booking_conflicts(sc.schedule), [])

        resp = self._client().post(
            self._url("academics:timetable_publish", schedule_id=sc.schedule.id)
        )
        self.assertEqual(resp.status_code, 302)
        sc.schedule.refresh_from_db()
        self.assertEqual(sc.schedule.status, "PUBLISHED")
        self.assertIsNotNone(sc.schedule.published_at)

    def test_publish_succeeds_for_linked_room_with_no_booking(self):
        sc = self._scenario(link_room=True)
        self.assertEqual(find_schedule_booking_conflicts(sc.schedule), [])
        resp = self._client().post(
            self._url("academics:timetable_publish", schedule_id=sc.schedule.id)
        )
        self.assertEqual(resp.status_code, 302)
        sc.schedule.refresh_from_db()
        self.assertEqual(sc.schedule.status, "PUBLISHED")

    def test_publish_succeeds_for_unlinked_room_backcompat(self):
        # Room NOT linked to a resource — even an overlapping booking is ignored.
        sc = self._scenario(link_room=False)
        resource = BookableResource.objects.create(
            school=self.school, name=f"Unlinked-{sc.uid}", capacity=1
        )
        occ_start, occ_end = self._first_occurrence()
        self._confirmed_booking(
            resource=resource,
            start=occ_start + timedelta(minutes=30),
            end=occ_end + timedelta(minutes=30),
            title="Irrelevant",
        )
        self.assertEqual(find_schedule_booking_conflicts(sc.schedule), [])
        resp = self._client().post(
            self._url("academics:timetable_publish", schedule_id=sc.schedule.id)
        )
        self.assertEqual(resp.status_code, 302)
        sc.schedule.refresh_from_db()
        self.assertEqual(sc.schedule.status, "PUBLISHED")

    # -- review clash panel names the conflict -----------------------------

    def test_review_panel_names_booking_conflict(self):
        sc = self._scenario(link_room=True)
        occ_start, occ_end = self._first_occurrence()
        self._confirmed_booking(
            resource=sc.resource,
            start=occ_start + timedelta(minutes=30),
            end=occ_end + timedelta(minutes=30),
            title="Staff meeting",
        )
        resp = self._client().get(
            self._url("academics:timetable_review", schedule_id=sc.schedule.id)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "room-booking clash")
        self.assertContains(resp, sc.room.name)
        self.assertFalse(resp.context["can_publish"])
        self.assertEqual(len(resp.context["booking_conflicts"]), 1)

    # -- term-week expansion is correct (pure, SQLite) ---------------------

    def test_slot_occurrences_expand_by_week(self):
        occs = list(
            _slot_occurrences(_TERM_START, _TERM_END, _SLOT_DAY, _SLOT_START, _SLOT_END)
        )
        # Every occurrence is on the slot's weekday, within the term, 7 days apart.
        self.assertTrue(occs)
        self.assertTrue(all(s.weekday() == _SLOT_DAY for s, _ in occs))
        self.assertTrue(all(_TERM_START <= s.date() <= _TERM_END for s, _ in occs))
        for (s0, _), (s1, _) in zip(occs, occs[1:]):
            self.assertEqual((s1.date() - s0.date()).days, 7)
        self.assertEqual(occs[0][0].time(), _SLOT_START)
        self.assertEqual(occs[0][1].time(), _SLOT_END)


@requires_postgres
@tag("tenants_rls")
class TimetableBookingConstraintPostgresTests(_BookingScenarioMixin, TestCase):
    """The btree_gist ExclusionConstraint guards the linked resource itself."""

    def setUp(self):
        self.school = School.objects.create(
            name="PG TT Booking",
            slug=f"pgtt-{uuid.uuid4().hex[:8]}",
            subdomain=f"pgtt-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )

    def test_db_exclusion_blocks_second_overlapping_booking_on_linked_resource(self):
        sc = self._scenario(link_room=True)
        occ_start, occ_end = self._first_occurrence()
        # First confirmed booking for the concrete class occurrence.
        create_resource_booking(
            school=self.school,
            resource=sc.resource,
            booked_by=None,
            title="Class hold",
            start=_aware(occ_start),
            end=_aware(occ_end),
        )
        # A second overlapping confirmed insert on the SAME resource must be
        # rejected by the exclusion constraint (bypass the service pre-check by
        # inserting through the ORM directly).
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ResourceBooking.objects.create(
                    school=self.school,
                    resource=sc.resource,
                    booked_by=None,
                    title="Overlapping",
                    time_range=(
                        _aware(occ_start + timedelta(minutes=30)),
                        _aware(occ_end + timedelta(minutes=30)),
                    ),
                    status=ResourceBooking.Status.CONFIRMED,
                )
