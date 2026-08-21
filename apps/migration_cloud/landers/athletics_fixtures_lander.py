"""Athletics fixtures lander — persists matches into ``apps.athletics.Fixture``
(and ``apps.athletics.FixtureResult`` when a score is present).

Domain ``athletics_fixtures``. Resolves the team by name (school-scoped)
and takes its ``season`` for the fixture, coerces the scheduled window to
datetimes, links an optional venue, then upserts the
:class:`apps.athletics.Fixture` on ``(team, opponent_name,
scheduled_start)``. When the row carries non-empty ``home_score`` /
``away_score`` columns a :class:`apps.athletics.FixtureResult` is upserted
against the fixture (OneToOne).

Graceful degradation (mirrors ``transport_assignment_lander``):
    * ``venue`` is an OPTIONAL FK — an unresolved ``EventVenue`` leaves it
      null (skip-when-unresolved) and the fixture still lands.
    * The row is quarantined only when it lacks what a ``Fixture`` cannot
      exist without: a resolvable team (its ``season`` + ``school``), a
      parseable ``scheduled_start``, or an ``opponent_name``.

Canonical row shape::

    {
        "team_name":       "Senior Boys 1st XI",
        "opponent_name":   "St. Mary's College",
        "fixture_type":    "home",            # home|away|neutral
        "venue":           "Main Field",      # optional — EventVenue by name
        "scheduled_start": "2026-04-10T15:00:00",
        "scheduled_end":   "2026-04-10T17:00:00",  # optional → defaults to start
        "home_score":      "3",               # optional int → FixtureResult
        "away_score":      "1",               # optional int → FixtureResult
        "status":          "completed",       # scheduled|confirmed|in_progress|completed|postponed|cancelled
    }

Upsert keys:
    * Fixture: ``(team, opponent_name, scheduled_start)``.
    * FixtureResult: ``(fixture,)`` OneToOne — only when a score is present.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Iterator

from django.conf import settings
from django.utils import timezone

from ._helpers import (
    coerce_date,
    coerce_int,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    record_row_error,
    record_row_note,
    row_savepoint,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import INVALID_REF, LANDER_ERROR, MISSING_REQUIRED


logger = logging.getLogger(__name__)

_VALID_FIXTURE_TYPES = ("home", "away", "neutral")
_VALID_STATUSES = (
    "scheduled", "confirmed", "in_progress", "completed", "postponed", "cancelled",
)
_VALID_OUTCOMES = ("win", "loss", "draw", "void")
_TEAM_NAME_CAP = 120
_OPPONENT_NAME_CAP = 200
_VENUE_NAME_CAP = 160  # magic-number-allow: mirrors school_events EventVenue.name max_length

_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y/%m/%d %H:%M",
)


def _coerce_datetime(value: Any) -> _dt.datetime | None:
    """Best-effort parse of a canonical datetime cell.

    Preserves time-of-day (unlike ``coerce_date``) so a match kickoff
    time survives the round-trip. Falls back to a date-only value at
    midnight, and makes the result timezone-aware when ``USE_TZ`` so the
    ``DateTimeField`` stores cleanly.
    """
    if value in (None, ""):
        return None
    parsed: _dt.datetime | None = None
    if isinstance(value, _dt.datetime):
        parsed = value
    elif isinstance(value, _dt.date):
        parsed = _dt.datetime.combine(value, _dt.time.min)
    else:
        s = str(value).strip()
        try:
            parsed = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            parsed = None
        if parsed is None:
            for fmt in _DATETIME_FORMATS:
                try:
                    parsed = _dt.datetime.strptime(s, fmt)
                    break
                except (TypeError, ValueError):
                    continue
        if parsed is None:
            d = coerce_date(s)
            if d is not None:
                parsed = _dt.datetime.combine(d, _dt.time.min)
    if parsed is None:
        return None
    if getattr(settings, "USE_TZ", False) and timezone.is_naive(parsed):
        try:
            parsed = timezone.make_aware(parsed, timezone.get_default_timezone())
        except Exception:  # noqa: BLE001 — ambiguous/imaginary local time; keep naive
            pass
    return parsed


class AthleticsFixturesLander(Lander):
    domain = "athletics_fixtures"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.athletics.models import Fixture, FixtureResult, Team
            from apps.school_events.models import EventVenue
        except ImportError as exc:
            raise LanderError(
                f"AthleticsFixturesLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        team_fields = model_field_names(Team)
        fixture_fields = model_field_names(Fixture)
        result_fields = model_field_names(FixtureResult)
        venue_fields = model_field_names(EventVenue)
        team_cache: dict[str, Any] = {}
        venue_cache: dict[str, Any] = {}

        for row_index, row in enumerate(canonical_rows):
            team_name = (row.get("team_name") or row.get("team") or "").strip()
            opponent_name = (row.get("opponent_name") or "").strip()
            scheduled_start = _coerce_datetime(row.get("scheduled_start"))
            if not team_name or not opponent_name or scheduled_start is None:
                record_row_error(
                    result,
                    row,
                    f"athletics_fixtures[row={row_index}]: "
                    f"missing team_name / opponent_name / scheduled_start",
                    reason_code=MISSING_REQUIRED,
                )
                continue

            team = self._resolve_team(Team, team_fields, team_cache, ctx, team_name)
            if team is None:
                record_row_error(
                    result,
                    row,
                    f"athletics_fixtures[row={row_index}]: "
                    f"no team named <redacted> (catalog not landed yet)",
                    reason_code=INVALID_REF,
                )
                logger.info(
                    "athletics_fixtures quarantine row=%d reason=team_unresolved",
                    row_index,
                )
                continue

            scheduled_end = (
                _coerce_datetime(row.get("scheduled_end")) or scheduled_start
            )
            fixture_type_raw = (row.get("fixture_type") or "").strip().lower()
            fixture_type = (
                fixture_type_raw if fixture_type_raw in _VALID_FIXTURE_TYPES else "home"
            )
            status_raw = (row.get("status") or "").strip().lower()
            status = status_raw if status_raw in _VALID_STATUSES else "scheduled"
            opponent_name = opponent_name[:_OPPONENT_NAME_CAP]

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = Fixture.objects.filter(
                    team=team,
                    opponent_name=opponent_name,
                    scheduled_start=scheduled_start,
                ).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue

            # OPTIONAL venue — skip-when-unresolved (never drop the row).
            venue_name = (row.get("venue") or "").strip()
            venue = None
            if venue_name:
                try:
                    venue = self._resolve_venue(
                        EventVenue, venue_fields, venue_cache, ctx, venue_name
                    )
                except Exception:  # noqa: BLE001 — optional FK, degrade to null
                    venue = None
                if venue is None:
                    logger.info(
                        "athletics_fixtures[row=%d]: venue unresolved; "
                        "leaving null (skip-when-unresolved)",
                        row_index,
                    )

            defaults: dict[str, Any] = {
                "season": team.season,
                "fixture_type": fixture_type,
                "scheduled_end": scheduled_end,
                "status": status,
                "venue": venue,
            }
            if "school" in fixture_fields and ctx.school is not None:
                defaults["school"] = ctx.school
            defaults = filter_to_model_fields(defaults, Fixture)

            lookup_kwargs: dict[str, Any] = {
                "team": team,
                "opponent_name": opponent_name,
                "scheduled_start": scheduled_start,
            }
            try:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                with row_savepoint():  # atomic-apply isolation
                    obj, created = Fixture.objects.update_or_create(
                        defaults=defaults, **lookup_kwargs,
                    )
            except (TypeError, ValueError) as exc:
                record_row_error(
                    result,
                    row,
                    f"athletics_fixtures[row={row_index}]: "
                    f"upsert input error: {type(exc).__name__}",
                    reason_code=LANDER_ERROR,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"athletics_fixtures[row={row_index}] upsert failed: "
                    f"{type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
                continue
            if created:
                result.created += 1
                result.created_ids.append(obj.pk)
            else:
                result.updated += 1
                result.updated_ids_with_old_values.append(
                    {"pk": obj.pk, "old": {k: getattr(obj, k, None)
                                           for k in defaults}}
                )
            record_id_mapping(
                ctx=ctx,
                legacy_id=(
                    f"{team_name}:{opponent_name}:{scheduled_start.isoformat()}"
                ),
                canonical_obj=obj,
                domain="athletics_fixtures",
            )

            # Optional score → FixtureResult (OneToOne on the fixture).
            self._maybe_land_result(
                FixtureResult, result_fields, ctx, row, obj, result,
            )
        return result

    def _maybe_land_result(
        self, FixtureResult, result_fields, ctx, row, fixture, result,
    ) -> None:
        raw_home = row.get("home_score")
        raw_away = row.get("away_score")
        if raw_home in (None, "") or raw_away in (None, ""):
            return
        home_score = coerce_int(raw_home)
        away_score = coerce_int(raw_away)
        if home_score is None or away_score is None:
            return
        outcome_raw = (row.get("outcome") or "").strip().lower()
        if outcome_raw in _VALID_OUTCOMES:
            outcome = outcome_raw
        else:
            # ``outcome`` is from OUR team's perspective. For an AWAY fixture our
            # team is the away side, so swap before comparing (mirrors
            # scheduling._outcome_for_team). Deriving straight from home>away
            # would invert the win/loss of every imported away match.
            if str(getattr(fixture, "fixture_type", "home")).lower() == "away":
                our_score, their_score = away_score, home_score
            else:
                our_score, their_score = home_score, away_score
            if our_score > their_score:
                outcome = "win"
            elif our_score < their_score:
                outcome = "loss"
            else:
                outcome = "draw"

        defaults: dict[str, Any] = {
            "home_score": home_score,
            "away_score": away_score,
            "outcome": outcome,
            "is_final": True,
        }
        if "school" in result_fields and ctx.school is not None:
            defaults["school"] = ctx.school
        defaults = filter_to_model_fields(defaults, FixtureResult)
        try:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            FixtureResult.objects.update_or_create(
                fixture=fixture, defaults=defaults,
            )
        except Exception as exc:  # noqa: BLE001 — score is auxiliary; never abort
            record_row_note(
                result,
                f"athletics_fixtures result upsert failed for fixture "
                f"{getattr(fixture, 'pk', '?')}: {type(exc).__name__}",
            )

    def _resolve_team(self, Team, team_fields, cache, ctx, name):
        """Resolve a Team by name (school-scoped) — read-only, cached."""
        key = f"{getattr(ctx.school, 'pk', '')}:{name.lower()}"
        if key in cache:
            return cache[key]
        lookup: dict[str, Any] = {"name": name[:_TEAM_NAME_CAP]}
        if "school" in team_fields and ctx.school is not None:
            lookup["school"] = ctx.school
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
        team = Team.objects.filter(**lookup).select_related("season").first()
        cache[key] = team
        return team

    def _resolve_venue(self, EventVenue, venue_fields, cache, ctx, name):
        """Resolve an EventVenue by name (school-scoped) — read-only, cached."""
        key = f"{getattr(ctx.school, 'pk', '')}:{name.lower()}"
        if key in cache:
            return cache[key]
        lookup: dict[str, Any] = {"name": name[:_VENUE_NAME_CAP]}
        if "school" in venue_fields and ctx.school is not None:
            lookup["school"] = ctx.school
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
        venue = EventVenue.objects.filter(**lookup).first()
        cache[key] = venue
        return venue


register("athletics_fixtures", AthleticsFixturesLander())


__all__ = ["AthleticsFixturesLander"]
