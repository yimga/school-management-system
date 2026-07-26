"""Athletics memberships lander — persists roster rows into
``apps.athletics.TeamMembership``.

Domain ``athletics_memberships`` — the per-student side of the athletics
roster. Resolves the student (via the same ``student_external_id``
lookup the transport lander uses) and the team (by name, school-scoped),
then upserts the membership on ``(team, student)``.

Quarantine policy (mirrors ``transport_assignment_lander``):
    * The row is quarantined (``quarantined += 1``; ``continue``) when the
      student can't be resolved — the join has no meaning without it.
    * A membership FK'd to a team that hasn't landed yet cannot exist
      (``team`` is a non-null FK), so an unresolved team also quarantines
      the row rather than dropping it silently; a re-run after the team
      catalog lands recovers it.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "team_name":           "Senior Boys 1st XI",
        "jersey_number":       "9",          # optional int
        "position":            "Striker",    # optional
        "status":              "active",     # pending|active|injured|suspended|left
        "joined_date":         "2025-09-01", # optional → joined_at
    }

Upsert key: ``(team, student)``.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    coerce_int,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    resolve_student,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


logger = logging.getLogger(__name__)

_VALID_STATUSES = ("pending", "active", "injured", "suspended", "left")
_TEAM_NAME_CAP = 120
_POSITION_CAP = 48


class AthleticsMembershipsLander(Lander):
    domain = "athletics_memberships"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.athletics.models import Team, TeamMembership
            from apps.people.models import StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"AthleticsMembershipsLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        team_fields = model_field_names(Team)
        membership_fields = model_field_names(TeamMembership)
        team_cache: dict[str, Any] = {}

        for row_index, row in enumerate(canonical_rows):
            external_id = (row.get("student_external_id") or "").strip()
            team_name = (row.get("team_name") or row.get("team") or "").strip()
            if not external_id or not team_name:
                result.quarantined += 1
                result.errors.append(
                    f"athletics_memberships[row={row_index}]: "
                    f"missing student_external_id or team_name"
                )
                continue

            student = resolve_student(
                ctx=ctx,
                student_model=StudentProfile,
                lookup_field=student_lookup,
                external_id=external_id,
            )
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"athletics_memberships[row={row_index}]: "
                    f"no student with {student_lookup}=<redacted>"
                )
                logger.info(
                    "athletics_memberships quarantine row=%d reason=student_unresolved",
                    row_index,
                )
                continue

            team = self._resolve_team(Team, team_fields, team_cache, ctx, team_name)
            if team is None:
                result.quarantined += 1
                result.errors.append(
                    f"athletics_memberships[row={row_index}]: "
                    f"no team named <redacted> (catalog not landed yet)"
                )
                logger.info(
                    "athletics_memberships quarantine row=%d reason=team_unresolved",
                    row_index,
                )
                continue

            jersey_number = coerce_int(row.get("jersey_number"))
            position = (row.get("position") or "").strip()[:_POSITION_CAP]
            status_raw = (row.get("status") or "").strip().lower()
            status = status_raw if status_raw in _VALID_STATUSES else "pending"
            joined_at = coerce_date(row.get("joined_date") or row.get("joined_at"))

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = TeamMembership.objects.filter(
                    team=team, student=student
                ).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue

            defaults: dict[str, Any] = {
                "jersey_number": jersey_number,
                "position": position,
                "status": status,
                "joined_at": joined_at,
            }
            if "school" in membership_fields and ctx.school is not None:
                defaults["school"] = ctx.school
            defaults = filter_to_model_fields(defaults, TeamMembership)

            lookup_kwargs: dict[str, Any] = {"team": team, "student": student}
            try:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                obj, created = TeamMembership.objects.update_or_create(
                    defaults=defaults, **lookup_kwargs,
                )
            except (TypeError, ValueError) as exc:
                result.quarantined += 1
                result.errors.append(
                    f"athletics_memberships[row={row_index}]: "
                    f"upsert input error: {type(exc).__name__}"
                )
                continue
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"athletics_memberships[row={row_index}] upsert failed: "
                    f"{type(exc).__name__}: {exc}"
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
                legacy_id=f"{external_id}:{team_name}",
                canonical_obj=obj,
                domain="athletics_memberships",
            )
        return result

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


register("athletics_memberships", AthleticsMembershipsLander())


__all__ = ["AthleticsMembershipsLander"]
