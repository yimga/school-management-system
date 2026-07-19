"""Fixture cancellation releases the venue — the missing CANCELLED producer.

Before this, ``FixtureVenueBooking.Status.CANCELLED`` had no reachable producer:
``schedule_fixture`` booked a venue (CONFIRMED) but nothing in the app ever
cancelled a fixture or freed its booking, so a mistaken/abandoned fixture pinned
its venue forever (the exclusion constraint fires only on ``status="confirmed"``).
``cancel_fixture`` sets the fixture CANCELLED and releases every confirmed venue
booking it holds, which also re-opens the slot for a replacement fixture.

The venue-booking assertions need Postgres (``FixtureVenueBooking.time_range`` is a
``DateTimeRangeField``, not creatable on SQLite); the status-transition + guard
tests run on the SQLite lane with ``book_venue=False``.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from apps.athletics.models import Fixture, FixtureVenueBooking
from apps.athletics.services.booking import (
    book_fixture_venue,
    overlapping_confirmed_count,
)
from apps.athletics.services.scheduling import (
    cancel_fixture,
    record_result,
    schedule_fixture,
)
from apps.athletics.tests.base import BaseAthleticsTestCase

requires_postgres = unittest.skipUnless(
    connection.vendor == "postgresql",
    "Venue booking persists a Postgres DateTimeRangeField (not creatable on SQLite).",
)


class CancelFixtureTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.now = timezone.now().replace(microsecond=0)

    def _scheduled(self, *, book_venue=False):
        return schedule_fixture(
            team=self.fx.team,
            opponent_name="St Mary's",
            fixture_type=Fixture.FixtureType.HOME,
            venue=self.fx.venue,
            start=self.now,
            end=self.now + timedelta(hours=2),
            book_venue=book_venue,
        )

    def test_cancel_sets_status_cancelled(self):
        fixture = self._scheduled()
        returned = cancel_fixture(fixture=fixture, actor=self.fx.teacher_user)
        self.assertEqual(returned.status, Fixture.Status.CANCELLED)
        fixture.refresh_from_db()
        self.assertEqual(fixture.status, Fixture.Status.CANCELLED)

    def test_cancel_is_idempotent(self):
        fixture = self._scheduled()
        cancel_fixture(fixture=fixture)
        # A second cancel must be a no-op, not an error.
        cancel_fixture(fixture=fixture)
        fixture.refresh_from_db()
        self.assertEqual(fixture.status, Fixture.Status.CANCELLED)

    def test_completed_fixture_cannot_be_cancelled(self):
        fixture = self._scheduled()
        record_result(fixture=fixture, home_score=2, away_score=1)
        fixture.refresh_from_db()
        self.assertEqual(fixture.status, Fixture.Status.COMPLETED)
        with self.assertRaises(ValueError):
            cancel_fixture(fixture=fixture)
        fixture.refresh_from_db()
        self.assertEqual(fixture.status, Fixture.Status.COMPLETED)

    @requires_postgres
    def test_cancel_releases_confirmed_venue_booking(self):
        fixture = self._scheduled(book_venue=True)
        self.assertTrue(
            fixture.venue_bookings.filter(
                status=FixtureVenueBooking.Status.CONFIRMED
            ).exists()
        )
        cancel_fixture(fixture=fixture)
        self.assertFalse(
            fixture.venue_bookings.filter(
                status=FixtureVenueBooking.Status.CONFIRMED
            ).exists()
        )
        self.assertTrue(
            fixture.venue_bookings.filter(
                status=FixtureVenueBooking.Status.CANCELLED
            ).exists()
        )

    @requires_postgres
    def test_cancel_frees_the_slot_for_a_replacement_fixture(self):
        # The decisive end-to-end proof: a confirmed booking blocks the slot; after
        # cancel, the SAME slot books again without a conflict.
        fixture = self._scheduled(book_venue=True)
        self.assertEqual(
            overlapping_confirmed_count(
                school=self.fx.school,
                venue=self.fx.venue,
                start=self.now,
                end=self.now + timedelta(hours=2),
            ),
            1,
        )
        cancel_fixture(fixture=fixture)
        self.assertEqual(
            overlapping_confirmed_count(
                school=self.fx.school,
                venue=self.fx.venue,
                start=self.now,
                end=self.now + timedelta(hours=2),
            ),
            0,
        )
        replacement = Fixture.objects.create(
            school=self.fx.school,
            team=self.fx.team,
            season=self.fx.season,
            opponent_name="Replacement",
            scheduled_start=self.now,
            scheduled_end=self.now + timedelta(hours=2),
        )
        # Would have raised BookingConflictError while the first booking stood.
        booking = book_fixture_venue(
            school=self.fx.school,
            venue=self.fx.venue,
            fixture=replacement,
            title="Replacement",
            start=self.now,
            end=self.now + timedelta(hours=2),
        )
        self.assertEqual(booking.status, FixtureVenueBooking.Status.CONFIRMED)

    @requires_postgres
    def test_cancel_without_booking_is_still_clean(self):
        # A fixture scheduled without booking a venue cancels with zero bookings.
        fixture = self._scheduled(book_venue=False)
        cancel_fixture(fixture=fixture)
        fixture.refresh_from_db()
        self.assertEqual(fixture.status, Fixture.Status.CANCELLED)
        self.assertFalse(fixture.venue_bookings.exists())


class CancelFixtureViewTests(BaseAthleticsTestCase):
    """The coach cancel route reaches the service (RBAC + team-scope enforced)."""

    def setUp(self):
        super().setUp()
        self.now = timezone.now().replace(microsecond=0)

    def _scheduled(self):
        return schedule_fixture(
            team=self.fx.team,
            opponent_name="St Mary's",
            fixture_type=Fixture.FixtureType.HOME,
            venue=self.fx.venue,
            start=self.now,
            end=self.now + timedelta(hours=2),
            book_venue=False,
        )

    def test_cancel_route_is_registered(self):
        # Athletics is mounted in the tenant host urlconf (config.tenant_urls), not
        # the default ROOT_URLCONF, so resolve against it explicitly.
        from django.urls import reverse

        url = reverse(
            "athletics:coach_cancel_fixture",
            kwargs={"fixture_id": 1},
            urlconf="config.tenant_urls",
        )
        self.assertTrue(url.endswith("/fixtures/1/cancel/"))
