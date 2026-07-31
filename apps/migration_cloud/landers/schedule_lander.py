"""Schedule (timetable) lander — preserves canonical schedule rows as custom records.

Canonical row shape (per ``ontology/catalog.py`` ``schedule``)::

    {
        "section_external_id": "SEC-9MATH-A",
        "day_of_week":         "Monday",   # or ISO 1..7
        "start_time":          "08:30",
        "end_time":            "09:30",
        "room":                "Lab-2",
    }

Design note (why DFV, not first-class ``ScheduleEntry``): the platform's
timetable model ``apps.academics.scheduling.ScheduleEntry`` is the OUTPUT of the
constraint-solving timetable engine — every row requires FKs to a ``Schedule``
(which itself needs a ``Term`` + ``InstructionShift``), a ``TimeSlot``, a ``Room``
row, a ``Subject``, a ``Classroom`` and a teacher ``User``, plus it enforces
per-plan double-booking unique constraints. A raw SIS timetable export cannot
manufacture that solved graph without inventing scheduling infrastructure, and
force-fitting it would IntegrityError-quarantine every row. So — exactly like
``payroll`` (needs PayrollRun/Employee) and ``compliance`` (region-scoped, no
``school`` FK) — the schedule domain PRESERVES each timetable slot losslessly as
a ``DynamicFieldValue`` custom record keyed to a stable
(section, day, start_time) identity. No data is dropped; the school can re-solve a
first-class timetable from these records via the scheduling engine after cutover.

Before this lander existed, ``schedule`` was classifiable (it is in
``ontology/catalog.py::DOMAINS`` with a full ontology and a reserved apply wave)
but had NO registered lander, so it fell through to the generic ``custom_fields``
catch-all. That still landed the rows as DFV, but silently and unlabelled;
registering an explicit domain lander makes the behaviour intentional, documented,
and consistent with the other two deliberate-DFV domains.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import persist_dfv_extras
from .base import Lander, LanderContext, LanderResult, register


class ScheduleLander(Lander):
    domain = "schedule"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        result = LanderResult()
        for row in canonical_rows:
            section = (
                row.get("section_external_id")
                or row.get("section_id")
                or row.get("class_id")
                or ""
            ).strip()
            day = (row.get("day_of_week") or row.get("day") or "").strip()
            start = (row.get("start_time") or row.get("begin_time") or "").strip()
            if not section:
                result.quarantined += 1
                result.errors.append(
                    f"schedule: missing section_external_id in {row!r}"
                )
                continue
            # Stable per-slot identity → re-runs update the same custom record,
            # distinct (day, start_time) slots stay distinct.
            record_key = f"{section}:{day or 'na'}:{start or 'na'}"[:64]
            record = {k: str(v) for k, v in row.items() if v not in (None, "")}

            if ctx.dry_run:
                result.created += 1
                continue
            try:
                persist_dfv_extras(
                    ctx=ctx,
                    entity_type="schedule",
                    entity_id=record_key,
                    extras={"record": record},
                    result=result,
                )
                result.created += 1
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"schedule preserve failed for {section} {day} {start}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("schedule", ScheduleLander())
