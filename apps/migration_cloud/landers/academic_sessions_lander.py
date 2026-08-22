"""OneRoster ``academicSessions`` → ``apps.academics`` AcademicYear / Term (audit D-3).

OneRoster ships calendar sessions (``schoolYear`` / ``semester`` / ``term`` /
``gradingPeriod``) in ``academicSessions.csv``. Before this lander those rows
fell through to ``custom_fields`` — so a OneRoster import produced NO real terms,
and grades (which upsert on student + TERM + subject) had nothing to bind to.

This lander lands the sessions as first-class ``AcademicYear`` + ``Term`` rows in
wave 0 (before enrollment / grades), the same academic-scaffold slot the
``structure`` lander occupies for SPLITs.

Two-pass over the rows (materialised, since ``canonical_rows`` is an iterator):

  * Pass 1 provisions ``AcademicYear`` rows (``type == schoolYear``, or a row's
    ``school_year`` value) and remembers each by its OneRoster ``sourcedId`` so
    terms can resolve their parent.
  * Pass 2 provisions ``Term`` rows under their resolved parent year.

Rows that cannot resolve are quarantined WITH their source row (audit C-4
``record_row_error``), never silently dropped. Never mutates an existing
AcademicYear/Term (the target's own calendar wins) — it upserts by name.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterator

from ._helpers import coerce_date, model_field_names, maybe_stall_pulse, record_row_error, row_savepoint
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED

# Session ``type`` tokens (normalised: lowercased, spaces stripped) that denote a
# whole academic YEAR rather than a term/period within it.
_YEAR_TYPES = {"schoolyear", "school_year", "year", "academicyear"}


def _fallback_year_start() -> _dt.date:
    """A sane academic-year start when a session row carries no dates.

    AcademicYear.start_date / Term.start_date are non-null; a term whose
    startDate the export omitted still needs a value. Uses the current calendar
    year's northern-hemisphere academic-year start; the operator can correct it
    afterward. Kept local so the lander has no cross-lander import coupling.
    """
    return _dt.date(_dt.date.today().year, 9, 1)


def _fallback_year_end() -> _dt.date:
    return _dt.date(_dt.date.today().year + 1, 6, 30)


def _norm_type(row: dict[str, Any]) -> str:
    return (row.get("session_type") or "").strip().lower().replace(" ", "").replace("_", "")


def _year_name(row: dict[str, Any]) -> str:
    return (
        (row.get("school_year") or "").strip()
        or (row.get("session_title") or "").strip()
    )


class AcademicSessionsLander(Lander):
    """Land OneRoster academic sessions as AcademicYear / Term rows."""

    domain = "academic_sessions"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.academics.models import AcademicYear, Term
        except Exception as exc:  # noqa: BLE001
            raise LanderError(
                f"AcademicSessionsLander could not import AcademicYear / Term: {exc!s}"
            ) from exc

        result = LanderResult()
        rows = list(canonical_rows)  # lander-stream-allow: two-pass-oneroster-session-parent-resolution
        school = getattr(ctx, "school", None)
        year_fields = model_field_names(AcademicYear)
        term_fields = model_field_names(Term)

        year_by_extid: dict[str, Any] = {}   # sourcedId -> AcademicYear (term parent resolution)
        year_by_name: dict[str, Any] = {}    # name -> AcademicYear (dedupe within this run)

        def _resolve_or_make_year(name, *, start=None, end=None):
            name = (name or "").strip()[:50] or "Imported Year"
            if name in year_by_name:
                return year_by_name[name]
            qs = AcademicYear.objects.all()  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
            if "school" in year_fields and school is not None:
                qs = qs.filter(school=school)
            obj = qs.filter(name=name).order_by("pk").first()
            if obj is None:
                if ctx.dry_run:
                    year_by_name[name] = None
                    return None
                kwargs: dict[str, Any] = {
                    "name": name,
                    "start_date": start or _fallback_year_start(),
                    "end_date": end or _fallback_year_end(),
                }
                if "school" in year_fields and school is not None:
                    kwargs["school"] = school
                with row_savepoint():  # atomic-apply isolation (see _helpers.row_savepoint)
                    obj = AcademicYear.objects.create(**kwargs)
                result.created_ids.append(obj.pk)
                result.created += 1
            year_by_name[name] = obj
            return obj

        # Pass 1 — years.
        for row_index, row in enumerate(rows):
            maybe_stall_pulse(every=25, counter=row_index)
            if _norm_type(row) not in _YEAR_TYPES:
                continue
            year = _resolve_or_make_year(
                _year_name(row),
                start=coerce_date(row.get("session_start")),
                end=coerce_date(row.get("session_end")),
            )
            extid = (row.get("session_external_id") or "").strip()
            if extid and year is not None:
                year_by_extid[extid] = year

        # Pass 2 — terms / periods.
        for row_index, row in enumerate(rows):
            maybe_stall_pulse(every=25, counter=row_index)
            if _norm_type(row) in _YEAR_TYPES:
                continue
            title = (row.get("session_title") or "").strip()
            if not title:
                record_row_error(
                    result, row, "academic_sessions: term row missing title",
                    reason_code=MISSING_REQUIRED, field="session_title",
                )
                continue

            parent_ext = (row.get("parent_session_external_id") or "").strip()
            year = year_by_extid.get(parent_ext) if parent_ext else None
            if year is None:
                year = _resolve_or_make_year(_year_name(row) or title)
            if year is None:  # dry-run: parent year would have been created
                result.skipped += 1
                continue

            name = title[:20]
            # Upsert by (academic_year, name) — Term's own unique_together — so a
            # re-run of the same bundle never duplicates a term.
            existing = Term.objects.filter(  # tenant-isolation-allow: academic_year is school-bound; scoped via its parent
                academic_year=year, name=name
            ).first()
            if existing is not None:
                result.updated += 1
                result.updated_ids_with_old_values.append({"id": existing.pk})
                continue
            if ctx.dry_run:
                result.skipped += 1
                continue

            kwargs = {
                "academic_year": year,
                "name": name,
                "custom_label": title[:30],
                "start_date": coerce_date(row.get("session_start"))
                or getattr(year, "start_date", None)
                or _fallback_year_start(),
                "end_date": coerce_date(row.get("session_end"))
                or getattr(year, "end_date", None)
                or _fallback_year_end(),
            }
            if "school" in term_fields and school is not None:
                kwargs["school"] = school
            try:
                with row_savepoint():
                    term = Term.objects.create(**kwargs)
            except Exception as exc:  # noqa: BLE001 — quarantine, don't abort the bundle
                # A custom_label / position uniqueness collision (two sessions whose
                # titles truncate alike) surfaces here; record the row for review.
                record_row_error(
                    result, row,
                    f"academic_sessions: could not create term {name!r}: {type(exc).__name__}",
                    reason_code=LANDER_ERROR,
                )
                continue
            result.created_ids.append(term.pk)
            result.created += 1

        return result


register("academic_sessions", AcademicSessionsLander())
