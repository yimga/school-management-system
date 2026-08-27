"""Fixture scheduling and result recording.

``schedule_fixture`` creates a fixture inside an atomic block and (optionally)
books its venue in the same transaction, so a booking conflict rolls the whole
schedule attempt back. ``record_result`` upserts the score and completes the
fixture.
"""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


@transaction.atomic
def schedule_fixture(
    *,
    team,
    opponent_name: str,
    fixture_type: str,
    venue=None,
    start,
    end,
    actor=None,
    book_venue: bool = True,
):
    """Schedule a fixture for ``team``; optionally book the venue atomically.

    Requires the team's season to be ACTIVE. When ``book_venue`` and a venue is
    given, a ``BookingConflictError`` from the venue booking aborts the whole
    atomic transaction (the fixture is rolled back with it).
    """
    from apps.athletics.models import Fixture, Season

    if end <= start:
        raise ValueError("end must be after start")
    season = team.season
    if season.status != Season.Status.ACTIVE:
        raise ValueError("cannot schedule a fixture outside an ACTIVE season")

    fixture = Fixture.objects.create(
        school=team.school,
        team=team,
        season=season,
        opponent_name=opponent_name,
        fixture_type=fixture_type,
        venue=venue,
        scheduled_start=start,
        scheduled_end=end,
        status=Fixture.Status.SCHEDULED,
        created_by=actor if getattr(actor, "pk", None) else None,
    )

    if book_venue and venue is not None:
        from apps.athletics.services.booking import book_fixture_venue

        book_fixture_venue(
            school=team.school,
            venue=venue,
            fixture=fixture,
            title=f"{team.name} vs {opponent_name}",
            start=start,
            end=end,
        )

    if fixture.fixture_type == Fixture.FixtureType.AWAY:
        _plan_away_travel(fixture)

    return fixture


def _plan_away_travel(fixture) -> None:
    """Open the ``FixtureTravel`` row for an away fixture (route still unset).

    ``link_away_fixture_transport`` had no caller anywhere in the repo, so
    ``FixtureTravel`` -- a first-class model on the mounted tenant admin --
    was never created by the product and scheduling an AWAY fixture booked no
    transport at all. The service documents ``route=None`` as a valid state
    ("travel row without a route yet"), which is exactly what a just-scheduled
    away fixture needs: it becomes visible to transport planning instead of
    invisible to it, and the operator attaches the route afterwards.

    Best-effort inside its own savepoint: a transport problem must not roll back
    the fixture the coach just scheduled.
    """
    try:
        with transaction.atomic():
            from apps.athletics.services.transport import link_away_fixture_transport

            link_away_fixture_transport(fixture=fixture)
    except Exception:  # noqa: BLE001 -- transport never costs the fixture
        logger.warning(
            "away_fixture_travel_not_planned fixture=%s", fixture.pk, exc_info=True
        )


def _outcome_for_team(*, fixture_type: str, home_score: int, away_score: int) -> str:
    """Derive the WIN/LOSS/DRAW outcome from the scheduled team's perspective.

    ``home_score`` / ``away_score`` are the literal home/away scores; which side
    the scheduled team is on depends on the fixture type (AWAY => our team is the
    away side; HOME / NEUTRAL => our team is the home side by convention).
    """
    from apps.athletics.models import Fixture, FixtureResult

    if fixture_type == Fixture.FixtureType.AWAY:
        our_score, their_score = away_score, home_score
    else:
        our_score, their_score = home_score, away_score

    if our_score > their_score:
        return FixtureResult.Outcome.WIN
    if our_score < their_score:
        return FixtureResult.Outcome.LOSS
    return FixtureResult.Outcome.DRAW


@transaction.atomic
def record_result(*, fixture, home_score: int, away_score: int, actor=None):
    """Upsert a fixture's result, derive the outcome, and complete the fixture."""
    from apps.athletics.models import Fixture, FixtureResult

    home = int(home_score)
    away = int(away_score)
    outcome = _outcome_for_team(
        fixture_type=fixture.fixture_type, home_score=home, away_score=away
    )

    result, _created = FixtureResult.objects.update_or_create(
        fixture=fixture,
        defaults={
            "school": fixture.school,
            "home_score": home,
            "away_score": away,
            "outcome": outcome,
            "recorded_by": actor if getattr(actor, "pk", None) else None,
        },
    )

    if fixture.status != Fixture.Status.COMPLETED:
        fixture.status = Fixture.Status.COMPLETED
        fixture.save(update_fields=["status", "updated_at"])

    return result


@transaction.atomic
def cancel_fixture(*, fixture, actor=None):
    """Cancel a fixture and release every confirmed venue booking it holds.

    Idempotent: an already-CANCELLED fixture is returned unchanged. A COMPLETED
    fixture (a played match with a recorded result) cannot be cancelled — raise
    ``ValueError`` so the caller can surface it. Releasing the confirmed venue
    bookings is the whole point: without it a cancelled match would pin its venue
    forever, and the ``FixtureVenueBooking.CANCELLED`` branch had no producer at
    all — the exclusion constraint only fires on ``status="confirmed"`` rows, so a
    released booking also stops blocking the slot for a replacement fixture.
    """
    from apps.athletics.models import Fixture, FixtureVenueBooking
    from apps.athletics.services.booking import cancel_fixture_venue_booking

    if fixture.status == Fixture.Status.CANCELLED:
        return fixture
    if fixture.status == Fixture.Status.COMPLETED:
        raise ValueError("a completed fixture cannot be cancelled")

    fixture.status = Fixture.Status.CANCELLED
    fixture.save(update_fields=["status", "updated_at"])

    # Reverse relation is already scoped to this single fixture (one school).
    confirmed = fixture.venue_bookings.filter(  # tenant-isolation-allow: reverse-relation-on-single-fixture-already-school-scoped
        status=FixtureVenueBooking.Status.CONFIRMED
    )
    for booking in confirmed:
        cancel_fixture_venue_booking(booking=booking)

    return fixture


__all__ = ["schedule_fixture", "record_result", "cancel_fixture"]
