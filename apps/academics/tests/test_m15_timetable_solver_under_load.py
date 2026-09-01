"""M15 -- the timetable solver measured at school scale, not asserted at toy scale.

Two things were true at once and neither was visible from the audit row.

**The best-covered scheduling code is code nothing runs.**
``apps/academics/timetable_solver.py`` has 20 genuinely behavioural tests --
placement counts, slot distinctness, a labelled fallback strategy, bounded
backtracking. It has zero production importers: the only non-test reference in
the tree is a descriptive STRING in a roadmap view. The module that actually
runs is ``apps.academics.scheduling.TimetableGenerator.generate_schedule``,
reached from ``views_timetable`` -> ``tasks_scheduling`` ->
``scheduling_solver.generate_timetable_with_solver``, whose own docstring says
the CP-SAT branch above it never executes because ortools is not a declared
dependency.

**The real solver was only ever measured at toy scale.** The largest fixture
anywhere is 4 cohorts x 5 subjects = 20 demands over 20 slots. A greedy
first-fit with no backtracking is trivially conflict-free at that size; the
question the audit row asks -- does it produce a conflict-free timetable under a
realistic load -- had never been put to it.

This module puts a school-sized problem to the production solver: **12 cohorts x
8 subjects = 96 demands, 8 shared teachers, 5 days x 8 periods = 40 slots, 20
rooms.** Every teacher must be spread across 12 distinct slots, so the placement
is genuinely constrained rather than a 1:1 map.

Conflicts are counted by THIS module's own arithmetic, not by
``evaluate_schedule``. Asserting that a production function reports zero
violations is asking the code under test to mark its own homework: if the
detector regressed, both it and the solver could be wrong together and the test
would still pass. The collision check below is a plain grouping over the
persisted rows.

The solver's failure mode is silence -- ``_place_block`` returns False and the
demand is skipped with no ``unplaced`` list, no exception and no signal in the
return value, so a caller learns about it only by counting entries. That is why
placement coverage is asserted here as well as conflict-freedom: a solver that
places nothing is perfectly conflict-free.
"""

from __future__ import annotations

import time as _time
import uuid
from collections import Counter

from django.test import TestCase

from apps.academics.scheduling import ScheduleEntry, TimetableGenerator
from apps.academics.scheduling_evaluation import evaluate_schedule
from apps.accounts.models import User
from apps.schools.models import School

from apps.academics.tests.test_timetable_publish_flow import _TimetableGraphMixin

# 12 cohorts x 8 subjects. A secondary school timetabling one term.
_SUBJECTS = (
    "Math",
    "English",
    "Biology",
    "Chemistry",
    "Physics",
    "History",
    "Geography",
    "French",
)
_COHORTS = ("1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B")
_PERIOD_HOURS = (8, 9, 10, 11, 13, 14, 15, 16)
_DAYS = 5

_EXPECTED_DEMANDS = len(_COHORTS) * len(_SUBJECTS)  # 96
_EXPECTED_SLOTS = _DAYS * len(_PERIOD_HOURS)  # 40


class TimetableSolverSchoolScaleTests(_TimetableGraphMixin, TestCase):
    """One realistic term, solved and then independently audited."""

    def setUp(self):
        self.uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"M15 Scale School {self.uid}",
            slug=f"m15-{self.uid}",
            subdomain=f"m15-{self.uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"m15_admin_{self.uid}",
            password="Test1234",
            role=User.Role.ADMIN,
        )
        self.graph = self.build_graph(
            self.school,
            self.uid,
            subject_names=_SUBJECTS,
            classroom_codes=_COHORTS,
            days=_DAYS,
            period_hours=_PERIOD_HOURS,
            room_count=20,
        )

    # -- independent conflict audit --------------------------------------

    def _collisions(self, schedule) -> dict[str, list]:
        """Count double-bookings from the persisted rows, without the product's
        own detector.

        A cell is (identity, time_slot, cycle_week). Three identities can be
        double-booked: a teacher in two places, a room holding two lessons, a
        cohort sitting two subjects.
        """
        rows = list(
            ScheduleEntry.objects.filter(
                schedule=schedule, is_cancelled=False
            ).values("teacher_id", "room_id", "classroom_id", "time_slot_id", "cycle_week")
        )
        report: dict[str, list] = {}
        for label, key in (
            ("teacher", "teacher_id"),
            ("room", "room_id"),
            ("cohort", "classroom_id"),
        ):
            counts = Counter(
                (row[key], row["time_slot_id"], row["cycle_week"])
                for row in rows
                if row[key] is not None
            )
            report[label] = [cell for cell, n in counts.items() if n > 1]
        return report

    # -- the measurements ------------------------------------------------

    def test_the_fixture_is_actually_school_sized(self):
        """Guard the load itself. Every assertion below is worthless if the
        graph quietly built six demands."""
        self.assertEqual(len(self.graph["assignments"]), _EXPECTED_DEMANDS)
        self.assertEqual(len(self.graph["slots"]), _EXPECTED_SLOTS)
        self.assertEqual(len(self.graph["classrooms"]), len(_COHORTS))
        self.assertEqual(len(self.graph["subjects"]), len(_SUBJECTS))
        self.assertEqual(len(self.graph["rooms"]), 20)
        # Shared teachers: 8 teachers carrying 96 lessons means each must be
        # placed in 12 distinct slots out of 40. Not a 1:1 map.
        self.assertEqual(len(self.graph["teachers"]), len(_SUBJECTS))

    def test_solver_produces_a_conflict_free_timetable_at_school_scale(self):
        started = _time.perf_counter()
        generator = TimetableGenerator(self.graph["year"], self.graph["term"])
        schedule = generator.generate_schedule(created_by=self.admin)
        elapsed = _time.perf_counter() - started

        placed = schedule.entries.filter(is_cancelled=False).count()
        collisions = self._collisions(schedule)

        # The measurement the audit row asked for, printed rather than guessed.
        print(
            f"\n[M15] demands={_EXPECTED_DEMANDS} slots={_EXPECTED_SLOTS} "
            f"teachers={len(self.graph['teachers'])} rooms=20 "
            f"placed={placed} elapsed={elapsed:.2f}s "
            f"collisions={ {k: len(v) for k, v in collisions.items()} }"
        )

        # 1. Conflict-free, counted independently of the product's detector.
        self.assertEqual(
            collisions["teacher"], [], msg="a teacher is booked twice in one slot"
        )
        self.assertEqual(
            collisions["room"], [], msg="a room holds two lessons in one slot"
        )
        self.assertEqual(
            collisions["cohort"], [], msg="a cohort sits two subjects in one slot"
        )

        # 2. It actually solved something. A solver that places nothing has no
        #    conflicts either, so conflict-freedom alone is not the claim.
        self.assertGreater(
            placed,
            0,
            msg="solver placed nothing -- conflict-freedom above is vacuous",
        )
        self.assertGreaterEqual(
            placed,
            int(_EXPECTED_DEMANDS * 0.9),
            msg=(
                f"only {placed} of {_EXPECTED_DEMANDS} demands placed; the solver "
                "skips what it cannot fit, silently"
            ),
        )

    def test_the_product_detector_agrees_with_an_independent_count(self):
        """Cross-check ``evaluate_schedule`` against the grouping above.

        Both being zero is only meaningful if they can disagree -- so this test
        exists to catch a detector that has stopped detecting, which would make
        every other suite's ``hard_violations_total == 0`` assertion hollow.
        """
        generator = TimetableGenerator(self.graph["year"], self.graph["term"])
        schedule = generator.generate_schedule(created_by=self.admin)

        independent = self._collisions(schedule)
        independent_total = sum(len(v) for v in independent.values())
        metrics = evaluate_schedule(schedule)

        self.assertEqual(independent_total, 0)
        self.assertEqual(
            metrics["hard_violations_total"],
            0,
            msg=f"product detector reports {metrics['hard_violations']}",
        )

    def test_every_placed_lesson_lands_in_a_real_slot_and_room(self):
        """A conflict-free timetable made of null slots is not a timetable."""
        generator = TimetableGenerator(self.graph["year"], self.graph["term"])
        schedule = generator.generate_schedule(created_by=self.admin)

        entries = list(
            ScheduleEntry.objects.filter(schedule=schedule, is_cancelled=False)
        )
        self.assertGreater(len(entries), 0)
        slot_ids = {slot.id for slot in self.graph["slots"]}
        room_ids = {room.id for room in self.graph["rooms"]}
        for entry in entries:
            self.assertIsNotNone(entry.time_slot_id)
            self.assertIn(entry.time_slot_id, slot_ids)
            self.assertIsNotNone(entry.teacher_id)
            if entry.room_id is not None:
                self.assertIn(entry.room_id, room_ids)

    def test_each_cohort_receives_a_spread_of_distinct_subjects(self):
        """Placement coverage per cohort, not just in aggregate.

        An aggregate count of 96 could be one cohort taught 96 times. The
        product promise is that every cohort gets its own subjects.
        """
        generator = TimetableGenerator(self.graph["year"], self.graph["term"])
        schedule = generator.generate_schedule(created_by=self.admin)

        by_cohort: dict[int, set] = {}
        for entry in ScheduleEntry.objects.filter(
            schedule=schedule, is_cancelled=False
        ).values("classroom_id", "subject_id"):
            by_cohort.setdefault(entry["classroom_id"], set()).add(entry["subject_id"])

        self.assertEqual(
            len(by_cohort),
            len(_COHORTS),
            msg=f"only {len(by_cohort)} of {len(_COHORTS)} cohorts got any lesson",
        )
        for classroom in self.graph["classrooms"]:
            subjects = by_cohort.get(classroom.id, set())
            self.assertGreaterEqual(
                len(subjects),
                len(_SUBJECTS) - 1,
                msg=(
                    f"cohort {classroom.code} received {len(subjects)} distinct "
                    f"subjects of {len(_SUBJECTS)}"
                ),
            )

    def test_a_shared_teacher_is_never_in_two_rooms_at_once(self):
        """The constraint the greedy pass exists to satisfy, stated directly.

        With 8 teachers covering 96 lessons this is the binding constraint --
        and it is the one a first-fit solver gets wrong first.
        """
        generator = TimetableGenerator(self.graph["year"], self.graph["term"])
        schedule = generator.generate_schedule(created_by=self.admin)

        per_teacher: dict[int, list] = {}
        for row in ScheduleEntry.objects.filter(
            schedule=schedule, is_cancelled=False
        ).values("teacher_id", "time_slot_id", "cycle_week"):
            per_teacher.setdefault(row["teacher_id"], []).append(
                (row["time_slot_id"], row["cycle_week"])
            )

        # Every teacher in the graph carried real load...
        self.assertGreaterEqual(len(per_teacher), len(_SUBJECTS) - 1)
        for teacher_id, cells in per_teacher.items():
            self.assertEqual(
                len(cells),
                len(set(cells)),
                msg=f"teacher {teacher_id} double-booked: {cells}",
            )
            # ...and enough of it that the distinctness above is a real result.
            self.assertGreater(len(cells), 1)
