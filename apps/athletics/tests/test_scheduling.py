"""Fixture scheduling + result outcome derivation.

``schedule_fixture`` requires the team's season to be ACTIVE and (when
``book_venue``) books the venue in the same atomic block, so a booking conflict
rolls the whole schedule back. ``record_result`` derives WIN/LOSS/DRAW from the
scheduled team's perspective, which flips for an AWAY fixture.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from apps.athletics.models import Fixture, FixtureResult, Season
from apps.athletics.services.booking import BookingConflictError, book_fixture_venue
from apps.athletics.services.scheduling import record_result, schedule_fixture
from apps.athletics.tests.base import BaseAthleticsTestCase

requires_postgres = unittest.skipUnless(
    connection.vendor == "postgresql",
    "Venue booking persists a Postgres DateTimeRangeField (not creatable on SQLite).",
)


class ScheduleFixtureTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.now = timezone.now().replace(microsecond=0)

    def test_schedule_in_active_season_succeeds(self):
        # book_venue=False keeps this on the SQLite lane (no DateTimeRangeField write).
        fixture = schedule_fixture(
            team=self.fx.team,
            opponent_name="St Mary's",
            fixture_type=Fixture.FixtureType.HOME,
            venue=self.fx.venue,
            start=self.now,
            end=self.now + timedelta(hours=2),
            book_venue=False,
        )
        self.assertIsNotNone(fixture.pk)
        self.assertEqual(fixture.season_id, self.fx.season.pk)
        self.assertEqual(fixture.venue_id, self.fx.venue.pk)
        self.assertEqual(fixture.status, Fixture.Status.SCHEDULED)

    @requires_postgres
    def test_schedule_books_venue_atomically(self):
        fixture = schedule_fixture(
            team=self.fx.team,
            opponent_name="St Mary's",
            fixture_type=Fixture.FixtureType.HOME,
            venue=self.fx.venue,
            start=self.now,
            end=self.now + timedelta(hours=2),
            book_venue=True,
        )
        self.assertTrue(fixture.venue_bookings.filter(status="confirmed").exists())

    def test_schedule_outside_active_season_rejected(self):
        self.fx.season.status = Season.Status.PLANNING
        self.fx.season.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            schedule_fixture(
                team=self.fx.team,
                opponent_name="St Mary's",
                fixture_type=Fixture.FixtureType.HOME,
                start=self.now,
                end=self.now + timedelta(hours=2),
                book_venue=False,
            )

    def test_end_before_start_rejected(self):
        with self.assertRaises(ValueError):
            schedule_fixture(
                team=self.fx.team,
                opponent_name="St Mary's",
                fixture_type=Fixture.FixtureType.HOME,
                start=self.now + timedelta(hours=2),
                end=self.now,
                book_venue=False,
            )

    @requires_postgres
    def test_booking_conflict_rolls_back_the_fixture(self):
        # Pre-book the venue for the slot so the scheduled fixture's booking conflicts.
        pre_fixture = Fixture.objects.create(
            school=self.fx.school, team=self.fx.team, season=self.fx.season,
            opponent_name="Pre", scheduled_start=self.now,
            scheduled_end=self.now + timedelta(hours=2),
        )
        book_fixture_venue(
            school=self.fx.school, venue=self.fx.venue, fixture=pre_fixture,
            title="Pre", start=self.now, end=self.now + timedelta(hours=2),
        )
        before = Fixture.objects.count()
        with self.assertRaises(BookingConflictError):
            schedule_fixture(
                team=self.fx.team,
                opponent_name="Conflicting",
                fixture_type=Fixture.FixtureType.HOME,
                venue=self.fx.venue,
                start=self.now + timedelta(minutes=30),
                end=self.now + timedelta(hours=1),
                book_venue=True,
            )
        # The would-be fixture was rolled back with the failed booking.
        self.assertEqual(Fixture.objects.count(), before)


class RecordResultTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.now = timezone.now().replace(microsecond=0)

    def _fixture(self, fixture_type):
        return Fixture.objects.create(
            school=self.fx.school, team=self.fx.team, season=self.fx.season,
            opponent_name="Opp", fixture_type=fixture_type,
            scheduled_start=self.now, scheduled_end=self.now + timedelta(hours=2),
        )

    def test_home_win(self):
        fixture = self._fixture(Fixture.FixtureType.HOME)
        result = record_result(fixture=fixture, home_score=3, away_score=1)
        self.assertEqual(result.outcome, FixtureResult.Outcome.WIN)
        fixture.refresh_from_db()
        self.assertEqual(fixture.status, Fixture.Status.COMPLETED)

    def test_away_fixture_higher_away_score_is_win(self):
        # Our team is the AWAY side, so away_score > home_score is a WIN for us.
        fixture = self._fixture(Fixture.FixtureType.AWAY)
        result = record_result(fixture=fixture, home_score=1, away_score=3)
        self.assertEqual(result.outcome, FixtureResult.Outcome.WIN)

    def test_away_fixture_lower_away_score_is_loss(self):
        fixture = self._fixture(Fixture.FixtureType.AWAY)
        result = record_result(fixture=fixture, home_score=4, away_score=2)
        self.assertEqual(result.outcome, FixtureResult.Outcome.LOSS)

    def test_home_loss(self):
        fixture = self._fixture(Fixture.FixtureType.HOME)
        result = record_result(fixture=fixture, home_score=0, away_score=2)
        self.assertEqual(result.outcome, FixtureResult.Outcome.LOSS)

    def test_draw(self):
        fixture = self._fixture(Fixture.FixtureType.NEUTRAL)
        result = record_result(fixture=fixture, home_score=2, away_score=2)
        self.assertEqual(result.outcome, FixtureResult.Outcome.DRAW)

    def test_record_result_is_idempotent_upsert(self):
        fixture = self._fixture(Fixture.FixtureType.HOME)
        record_result(fixture=fixture, home_score=1, away_score=0)
        record_result(fixture=fixture, home_score=2, away_score=1)
        self.assertEqual(FixtureResult.objects.filter(fixture=fixture).count(), 1)
        result = FixtureResult.objects.get(fixture=fixture)
        self.assertEqual(result.home_score, 2)
        self.assertEqual(result.outcome, FixtureResult.Outcome.WIN)
