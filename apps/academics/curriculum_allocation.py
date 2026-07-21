"""Curriculum allocation — the one place lesson DEMAND is decided.

Item 2.3 of ``docs/PLATFORM_GLOBALIZATION_PROGRAM.md``.

WHAT WAS WRONG. The timetable generator had no demand model at all. It walked
``SubjectAssignment`` rows and placed exactly one ``ScheduleEntry`` per row
(``apps/academics/scheduling.py``: the slot loop ended in ``break  # Move to
next demand.``). "One assignment == one lesson" is a hardcoded, invisible
allocation of one period per subject per week. There was no field anywhere in
``apps/`` named ``periods_per_week`` or any synonym; the only related concept
was ``LessonRequest.weekly_periods`` in ``apps/academics/timetable_solver.py``,
a standalone in-memory solver with no DB source for the number (it is
constructed only by its own unit tests) and which is NOT the wired production
path — see the deployment note at the top of ``scheduling_solver.py``.

WHAT THIS MODULE DOES. It turns ``CurriculumAllocation`` rows into typed
:class:`AllocationSpec` values and hands them to the generator, with a default
that is behaviourally identical to the old hardcoded one. A tenant with zero
allocation rows gets one period per subject per week in a one-week cycle —
exactly the timetable it has today. Nothing is re-scheduled by this landing.

RESOLUTION ORDER (most specific wins):
    1. an active allocation naming this term,
    2. an active allocation with ``term=NULL`` (year-wide),
    3. :data:`DEFAULT_ALLOCATION`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class AllocationSpec:
    """How much time one (class, subject) pair is owed, as the solver sees it.

    ``source`` records WHERE the numbers came from so callers (and tests) can
    tell a real allocation apart from the compatibility default without
    re-querying. It is never used for control flow inside the solver.
    """

    periods_per_week: int = 1
    block_length: int = 1
    cycle_length: int = 1
    source: str = "default"

    def __post_init__(self):
        # Defensive normalisation: DB check constraints enforce >= 1, but this
        # dataclass is also built from user-supplied dicts in the API layer,
        # and a zero here would silently schedule nothing at all.
        object.__setattr__(self, "periods_per_week", max(1, int(self.periods_per_week or 1)))
        object.__setattr__(self, "block_length", max(1, int(self.block_length or 1)))
        object.__setattr__(self, "cycle_length", max(1, int(self.cycle_length or 1)))

    @property
    def periods_per_cycle(self) -> int:
        """Total lessons across the whole rotation."""
        return self.periods_per_week * self.cycle_length

    def blocks(self) -> list[int]:
        """Split one week's allocation into consecutive-period blocks.

        ``periods_per_week=5, block_length=2`` -> ``[2, 2, 1]``. The remainder
        is emitted as a shorter trailing block rather than dropped, because
        dropping it would silently under-teach the subject — the failure mode
        this whole item exists to remove.
        """
        remaining = self.periods_per_week
        out: list[int] = []
        while remaining > 0:
            size = min(self.block_length, remaining)
            out.append(size)
            remaining -= size
        return out


#: The compatibility default. Deliberately equal to the behaviour the
#: generator hardcoded before item 2.3, so enabling curriculum allocation
#: cannot move a single existing lesson.
DEFAULT_ALLOCATION = AllocationSpec(
    periods_per_week=1, block_length=1, cycle_length=1, source="default"
)


def _spec_from_row(row) -> AllocationSpec:
    return AllocationSpec(
        periods_per_week=row.periods_per_week,
        block_length=row.block_length,
        cycle_length=row.cycle_length,
        source="term" if row.term_id else "year",
    )


def build_allocation_index(academic_year, term=None) -> dict:
    """Return ``{(classroom_id, subject_id): AllocationSpec}`` in ONE query.

    Both the term-scoped and the year-wide rows are fetched together and the
    term-scoped one wins; doing it in Python avoids a per-demand query inside
    the generator's placement loop.
    """
    from apps.academics.models import CurriculumAllocation

    if academic_year is None:
        return {}

    from django.db.models import Q

    scope = Q(term__isnull=True)
    if term is not None:
        scope |= Q(term=term)

    # tenant-isolation-allow: scoped via academic_year FK (tenant-bound); the
    # caller passes an already-resolved AcademicYear for one school.
    rows = CurriculumAllocation.objects.filter(
        academic_year=academic_year,
        is_active=True,
    ).filter(scope)

    index: dict = {}
    for row in rows:
        key = (row.classroom_id, row.subject_id)
        existing = index.get(key)
        # A term-scoped row overrides a year-wide one regardless of read order.
        if existing is not None and existing.source == "term" and not row.term_id:
            continue
        index[key] = _spec_from_row(row)
    return index


def resolve_allocation(
    classroom_id: int,
    subject_id: int,
    index: Optional[dict] = None,
    *,
    academic_year=None,
    term=None,
) -> AllocationSpec:
    """Allocation for one (class, subject) pair, falling back to the default.

    Pass ``index`` (from :func:`build_allocation_index`) inside a loop; the
    ``academic_year``/``term`` form is the convenience path for one-off calls.
    """
    if index is None:
        index = build_allocation_index(academic_year, term)
    return index.get((classroom_id, subject_id), DEFAULT_ALLOCATION)


def plan_cycle_length(specs: Iterable[AllocationSpec]) -> int:
    """The whole plan's rotation length = the longest cycle any subject asks for.

    A school running one subject on a 2-week rotation runs a 2-week timetable;
    everything else simply repeats its week within that rotation. Returns 1 for
    an empty plan, which keeps a school with no allocations on a plain weekly
    timetable.
    """
    longest = 1
    for spec in specs:
        if spec.cycle_length > longest:
            longest = spec.cycle_length
    return longest
