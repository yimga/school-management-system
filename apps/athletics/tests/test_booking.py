"""Fixture venue booking — double-booking guard.

``FixtureVenueBooking.time_range`` is a Postgres ``DateTimeRangeField`` and the
overlap guard is a gist ``ExclusionConstraint`` (both Postgres-only). On the
SQLite lane the field cannot even be INSERTed (`unrecognized token ":"`), so —
exactly like ``apps.schoolops.tests.test_resource_booking`` for the sibling
``ResourceBooking`` — the persistence/interval tests are ``@requires_postgres``
and run on the Postgres CI, while the SQLite lane covers the pre-write
validation (which raises before any range INSERT) and the model contract.

NOTE (discrepancy vs the task brief): the brief expected ``book_fixture_venue``
to raise ``BookingConflictError`` via a *SQLite* interval pre-check. It can't —
the first booking's ``DateTimeRangeField`` INSERT fails on SQLite before any
second overlapping booking exists to detect, so there is never a stored row for
``overlapping_confirmed_count`` to iterate. The interval guard is therefore
proven on Postgres (its own ``time_range__overlap`` fast path) alongside the DB
exclusion constraint. This mirrors the established ``schoolops`` booking tests.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.db import connection
from django.test import SimpleTestCase
from django.utils import timezone

from apps.athletics.models import Fixture, FixtureVenueBooking
from apps.athletics.services.booking import (
    BookingConflictError,
    _range_bounds,
    book_fixture_venue,
    cancel_fixture_venue_booking,
)
from apps.athletics.tests.base import BaseAthleticsTestCase
from apps.school_events.models import EventVenue
from apps.schools.models import School

requires_postgres = unittest.skipUnless(
    connection.vendor == "postgresql",
    "FixtureVenueBooking uses a Postgres DateTimeRangeField + gist ExclusionConstraint "
    "(cannot be persisted on SQLite).",
)


class VenueBookingValidationTests(BaseAthleticsTestCase):
    """SQLite-safe: pre-write validation + the model's exclusion-constraint contract."""

    def setUp(self):
        super().setUp()
        self.now = timezone.now().replace(microsecond=0)
        self.fixture = Fixture.objects.create(
            school=self.fx.school, team=self.fx.team, season=self.fx.season,
            opponent_name="Opp", scheduled_start=self.now,
            scheduled_end=self.now + timedelta(hours=2),
        )

    def test_model_declares_overlap_exclusion_constraint(self):
        names = {c.name for c in FixtureVenueBooking._meta.constraints}
        self.assertIn("exclude_overlapping_athletics_venue_bookings", names)

    def test_end_before_start_rejected(self):
        with self.assertRaises(ValueError):
            book_fixture_venue(
                school=self.fx.school, venue=self.fx.venue, fixture=self.fixture,
                title="Bad", start=self.now + timedelta(hours=2), end=self.now,
            )

    def test_venue_from_another_school_rejected(self):
        other_school = School.objects.create(
            name="Other School", slug="other-bk", subdomain="other-bk"
        )
        other_venue = EventVenue.objects.create(
            school=other_school, name="Foreign Field", code="foreign-field"
        )
        with self.assertRaises(ValueError):
            book_fixture_venue(
                school=self.fx.school, venue=other_venue, fixture=self.fixture,
                title="Cross tenant", start=self.now,
                end=self.now + timedelta(hours=2),
            )


@requires_postgres
class VenueBookingPersistenceTests(BaseAthleticsTestCase):
    """Postgres-only: the DateTimeRangeField persistence + interval overlap guard."""

    def setUp(self):
        super().setUp()
        self.now = timezone.now().replace(microsecond=0)
        self.fixture = self._fixture("Opp 1")

    def _fixture(self, opponent):
        return Fixture.objects.create(
            school=self.fx.school, team=self.fx.team, season=self.fx.season,
            opponent_name=opponent, scheduled_start=self.now,
            scheduled_end=self.now + timedelta(hours=2),
        )

    def test_overlapping_confirmed_second_raises(self):
        book_fixture_venue(
            school=self.fx.school, venue=self.fx.venue, fixture=self.fixture,
            title="Match 1", start=self.now, end=self.now + timedelta(hours=2),
        )
        with self.assertRaises(BookingConflictError):
            book_fixture_venue(
                school=self.fx.school, venue=self.fx.venue, fixture=self._fixture("Opp 2"),
                title="Match 2", start=self.now + timedelta(hours=1),
                end=self.now + timedelta(hours=3),
            )

    def test_non_overlapping_both_succeed(self):
        b1 = book_fixture_venue(
            school=self.fx.school, venue=self.fx.venue, fixture=self.fixture,
            title="Match 1", start=self.now, end=self.now + timedelta(hours=2),
        )
        b2 = book_fixture_venue(
            school=self.fx.school, venue=self.fx.venue, fixture=self._fixture("Opp 2"),
            title="Match 2", start=self.now + timedelta(hours=3),
            end=self.now + timedelta(hours=5),
        )
        self.assertIsNotNone(b1.pk)
        self.assertIsNotNone(b2.pk)

    def test_different_venues_overlap_both_succeed(self):
        other_venue = EventVenue.objects.create(
            school=self.fx.school, name="Second Field", code="second-field-a"
        )
        b1 = book_fixture_venue(
            school=self.fx.school, venue=self.fx.venue, fixture=self.fixture,
            title="Match 1", start=self.now, end=self.now + timedelta(hours=2),
        )
        b2 = book_fixture_venue(
            school=self.fx.school, venue=other_venue, fixture=self._fixture("Opp 2"),
            title="Match 2", start=self.now, end=self.now + timedelta(hours=2),
        )
        self.assertIsNotNone(b1.pk)
        self.assertIsNotNone(b2.pk)

    def test_cancelled_booking_does_not_block(self):
        b1 = book_fixture_venue(
            school=self.fx.school, venue=self.fx.venue, fixture=self.fixture,
            title="Match 1", start=self.now, end=self.now + timedelta(hours=2),
        )
        cancel_fixture_venue_booking(booking=b1)
        b2 = book_fixture_venue(
            school=self.fx.school, venue=self.fx.venue, fixture=self._fixture("Opp 2"),
            title="Match 2", start=self.now, end=self.now + timedelta(hours=2),
        )
        self.assertEqual(b2.status, FixtureVenueBooking.Status.CONFIRMED)


class RangeBoundsParsingTests(SimpleTestCase):
    """DB-free coverage of the SQLite-fallback range parser used by
    ``overlapping_confirmed_count`` on the non-Postgres lane.

    On SQLite a stored ``DateTimeRangeField`` round-trips as its canonical text
    ``'[lower,upper)'`` — a ``str`` whose ``.lower`` is the string method, so the
    pre-``_range_bounds`` code (``row.time_range.lower``) read a truthy bound
    method past its ``None`` guard and then crashed in ``_aware``. This proves
    the parser returns real ``datetime`` bounds (or a clean ``(None, None)``)
    from every shape the field can present. Sibling parity with
    ``apps.schoolops.booking_services._range_bounds``.
    """

    def test_parses_canonical_text_range_to_datetimes(self):
        lower, upper = _range_bounds(
            "[2026-01-01T10:00:00+00:00,2026-01-01T11:00:00+00:00)"
        )
        # The regression: bounds must be real datetimes, never the str.lower method.
        self.assertIsInstance(lower, datetime)
        self.assertIsInstance(upper, datetime)
        self.assertEqual(
            lower, datetime(2026, 1, 1, 10, 0, tzinfo=dt_timezone.utc)
        )
        self.assertEqual(
            upper, datetime(2026, 1, 1, 11, 0, tzinfo=dt_timezone.utc)
        )

    def test_reads_range_object_lower_upper_attrs(self):
        class _Range:
            lower = datetime(2026, 1, 1, 9, 0, tzinfo=dt_timezone.utc)
            upper = datetime(2026, 1, 1, 10, 0, tzinfo=dt_timezone.utc)

        lower, upper = _range_bounds(_Range())
        self.assertEqual(lower, _Range.lower)
        self.assertEqual(upper, _Range.upper)

    def test_none_and_empty_yield_no_bounds(self):
        self.assertEqual(_range_bounds(None), (None, None))
        self.assertEqual(_range_bounds("empty"), (None, None))
        self.assertEqual(_range_bounds(""), (None, None))
