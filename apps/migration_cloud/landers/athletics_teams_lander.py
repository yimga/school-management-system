"""Athletics teams lander — persists squads into ``apps.athletics.Team``.

Domain ``athletics_teams`` — the squad catalog for the athletics module.
Resolves (or provisions) the parent :class:`apps.athletics.Sport` and
:class:`apps.athletics.Season` a team belongs to, links an optional home
venue, then upserts the :class:`apps.athletics.Team` on ``(season, name)``.

Graceful degradation (mirrors ``transport_assignment_lander``):
    * ``Sport`` + ``Season`` are ``get_or_create``'d school-scoped so a
      teams bundle that arrives before any sport/season catalog still
      lands — the athletics scaffold is provisioned on the fly. Season
      dates the teams file does not carry default to today and can be
      corrected in-app (the row is never dropped for want of them).
    * ``home_venue`` is an OPTIONAL FK. When the named
      ``school_events.EventVenue`` hasn't landed yet (out-of-order
      bundle) the team is still created with ``home_venue=None``
      (skip-when-unresolved) — mirroring the transport lander's
      route-cache fallback, we NEVER drop the row. A later re-run after
      the venue lands fills it in without disturbing anything else.
    * The row is quarantined only when it lacks a field a ``Team`` cannot
      exist without (sport / season / team name).

Canonical row shape::

    {
        "sport":      "Football",
        "season":     "2025-2026 Fall",
        "team_name":  "Senior Boys 1st XI",
        "level":      "senior",             # optional
        "gender":     "boys",               # boys|girls|mixed
        "roster_cap": "23",                 # optional int
        "home_venue": "Main Field",         # optional — EventVenue by name
        "status":     "active",             # forming|active|disbanded
    }

Upsert key: ``(season, name)`` — matches ``Team`` unique_together.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Iterator

from django.utils.text import slugify

from ._helpers import (
    coerce_int,
    filter_to_model_fields,
    model_field_names,
    normalize_canonical_row,
    record_id_mapping,
    record_row_error,
    row_savepoint,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED


logger = logging.getLogger(__name__)

_VALID_GENDERS = ("boys", "girls", "mixed")
_VALID_STATUSES = ("forming", "active", "disbanded")
_NAME_CAP = 120
_LEVEL_CAP = 48
_SLUG_CAP = 40
_SPORT_NAME_CAP = 80
_VENUE_NAME_CAP = 160  # magic-number-allow: mirrors school_events EventVenue.name max_length


class AthleticsTeamsLander(Lander):
    domain = "athletics_teams"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.athletics.models import Season, Sport, Team
            from apps.school_events.models import EventVenue
        except ImportError as exc:
            raise LanderError(
                f"AthleticsTeamsLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        sport_fields = model_field_names(Sport)
        season_fields = model_field_names(Season)
        team_fields = model_field_names(Team)
        venue_fields = model_field_names(EventVenue)
        sport_cache: dict[str, Any] = {}
        season_cache: dict[str, Any] = {}
        venue_cache: dict[str, Any] = {}

        for row_index, row in enumerate(canonical_rows):
            row = normalize_canonical_row("athletics_teams", row, ctx)
            sport_name = (row.get("sport") or "").strip()
            season_name = (row.get("season") or "").strip()
            team_name = (row.get("team_name") or row.get("name") or "").strip()
            if not sport_name or not season_name or not team_name:
                record_row_error(
                    result,
                    row,
                    f"athletics_teams[row={row_index}]: "
                    f"missing sport / season / team_name",
                    reason_code=MISSING_REQUIRED,
                )
                continue

            level = (row.get("level") or "").strip()[:_LEVEL_CAP]
            gender_raw = (row.get("gender") or "").strip().lower()
            gender = gender_raw if gender_raw in _VALID_GENDERS else "mixed"
            status_raw = (row.get("status") or "").strip().lower()
            status = status_raw if status_raw in _VALID_STATUSES else "forming"
            # Deliberately NOT ``or DEFAULT_ROSTER_CAP``: a missing /
            # unparseable cap stays ``None`` here and is dropped by
            # ``filter_to_model_fields`` below, so the create takes the
            # column's own default and an update leaves the operator's value
            # alone. ``or``-ing a default in would ALSO swallow an explicit
            # 0 (a squad closed to new members), which the source did mean.
            roster_cap = coerce_int(row.get("roster_cap"))
            venue_name = (row.get("home_venue") or "").strip()

            # Resolve (or provision) the sport + season scaffold. In dry-run
            # we only read (create=False) so a would-be create still counts.
            create = not ctx.dry_run
            try:
                sport = self._resolve_sport(
                    Sport, sport_fields, sport_cache, ctx, sport_name, create=create
                )
                season = (
                    self._resolve_season(
                        Season, season_fields, season_cache, ctx, sport,
                        season_name, create=create,
                    )
                    if sport is not None
                    else None
                )
            except Exception as exc:  # noqa: BLE001 — quarantine, never abort bundle
                record_row_error(
                    result,
                    row,
                    f"athletics_teams[row={row_index}]: "
                    f"scaffold resolve failed: {type(exc).__name__}",
                    reason_code=LANDER_ERROR,
                )
                continue

            if season is None:
                if ctx.dry_run:
                    # Scaffold not present yet → the team would be created.
                    result.created += 1
                    continue
                record_row_error(
                    result,
                    row,
                    f"athletics_teams[row={row_index}]: could not provision season",
                    reason_code=LANDER_ERROR,
                )
                continue

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = Team.objects.filter(
                    season=season, name=team_name[:_NAME_CAP]
                ).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue

            # OPTIONAL home venue — skip-when-unresolved (never drop the row).
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
                        "athletics_teams[row=%d]: home_venue unresolved; "
                        "leaving null (skip-when-unresolved)",
                        row_index,
                    )

            defaults: dict[str, Any] = {
                "sport": sport,
                "level": level,
                "gender": gender,
                "status": status,
                "roster_cap": roster_cap,
                "home_venue": venue,
            }
            if "school" in team_fields and ctx.school is not None:
                defaults["school"] = ctx.school
            # Load-bearing beyond dropping unknown columns: it also drops the
            # ``None``/blank VALUES above, which is what keeps a null
            # ``roster_cap`` out of a NOT NULL column (and a null
            # ``home_venue`` from clearing a venue somebody set in-app).
            defaults = filter_to_model_fields(defaults, Team)

            lookup_kwargs: dict[str, Any] = {
                "season": season,
                "name": team_name[:_NAME_CAP],
            }
            try:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                with row_savepoint():  # atomic-apply isolation
                    obj, created = Team.objects.update_or_create(
                        defaults=defaults, **lookup_kwargs,
                    )
            except (TypeError, ValueError) as exc:
                record_row_error(
                    result,
                    row,
                    f"athletics_teams[row={row_index}]: "
                    f"upsert input error: {type(exc).__name__}",
                    reason_code=LANDER_ERROR,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"athletics_teams[row={row_index}] upsert failed: "
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
                legacy_id=f"{sport_name}:{season_name}:{team_name}",
                canonical_obj=obj,
                domain="athletics_teams",
            )
        return result

    # -- scaffold resolution helpers ---------------------------------------

    def _resolve_sport(
        self, Sport, sport_fields, cache, ctx, name, *, create,
    ):
        """Resolve a Sport by slug code (school-scoped); provision when create."""
        code = slugify(name)[:_SLUG_CAP] or "sport"
        key = f"{getattr(ctx.school, 'pk', '')}:{code}"
        if key in cache:
            return cache[key]
        lookup: dict[str, Any] = {"code": code}
        if "school" in sport_fields and ctx.school is not None:
            lookup["school"] = ctx.school
        if create:
            defaults = filter_to_model_fields({"name": name[:_SPORT_NAME_CAP]}, Sport)
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            sport, _ = Sport.objects.get_or_create(defaults=defaults, **lookup)
        else:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            sport = Sport.objects.filter(**lookup).first()
        cache[key] = sport
        return sport

    def _resolve_season(
        self, Season, season_fields, cache, ctx, sport, name, *, create,
    ):
        """Resolve a Season by (school, sport, name); provision when create.

        The teams file does not carry season start/end dates (both are
        required ``DateField``s), so a provisioned season defaults its
        window to today — corrected in-app later. Defaults only apply on
        first create, never on a match.
        """
        key = (
            f"{getattr(ctx.school, 'pk', '')}:"
            f"{getattr(sport, 'pk', '')}:{name.lower()}"
        )
        if key in cache:
            return cache[key]
        lookup: dict[str, Any] = {"sport": sport, "name": name[:_NAME_CAP]}
        if "school" in season_fields and ctx.school is not None:
            lookup["school"] = ctx.school
        if create:
            today = _dt.date.today()
            defaults = filter_to_model_fields(
                {"start_date": today, "end_date": today}, Season
            )
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            season, _ = Season.objects.get_or_create(defaults=defaults, **lookup)
        else:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            season = Season.objects.filter(**lookup).first()
        cache[key] = season
        return season

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


register("athletics_teams", AthleticsTeamsLander())


__all__ = ["AthleticsTeamsLander"]
