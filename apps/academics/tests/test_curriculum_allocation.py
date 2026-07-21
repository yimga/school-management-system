"""Item 2.3 — CurriculumAllocation is the timetable generator's demand model.

Every test here is a MUST-FIRE: delete the ``CurriculumAllocation`` lookup from
``TimetableGenerator.generate_schedule`` and the first three go red, because
before this item the generator placed exactly one entry per SubjectAssignment
and ``break``-ed.

``NoAllocationParityTests`` is the opposite guarantee: it pins the EXACT slot a
school with no allocation rows gets, so a future change to demand handling
cannot silently re-schedule an existing tenant.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from django.test import TestCase

from apps.academics.curriculum_allocation import (
    DEFAULT_ALLOCATION,
    AllocationSpec,
    build_allocation_index,
    plan_cycle_length,
    resolve_allocation,
)
from apps.academics.models import (
    AcademicYear,
    Classroom,
    CurriculumAllocation,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.academics.scheduling import Room, TimeSlot, TimetableGenerator
from apps.academics.scheduling_evaluation import evaluate_schedule
from apps.accounts.models import User
from apps.schools.models import School


class _GraphMixin:
    """A minimal, fully deterministic academic graph for one school."""

    def build(self, *, subject_names=("Math",), days=5, periods=2, rooms=2):
        uid = uuid.uuid4().hex[:8]
        self.uid = uid
        self.school = School.objects.create(
            name=f"Alloc School {uid}",
            slug=f"alloc-{uid}",
            subdomain=f"alloc-{uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"alloc_admin_{uid}", password="Test1234", role=User.Role.ADMIN
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name=f"2025/2026-{uid}",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        dept = Department.objects.create(
            school=self.school, name=f"Dept-{uid}", code=f"D{uid}"
        )
        self.specialty = Specialty.objects.create(
            school=self.school, department=dept, name="General", code=f"SP-{uid}"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=dept,
            name="Form 1",
            code=f"F1-{uid}",
        )
        self.subjects = []
        self.assignments = []
        for index, sname in enumerate(subject_names):
            subject = Subject.objects.create(school=self.school, name=f"{sname}-{uid}")
            teacher = User.objects.create_user(
                username=f"t_{sname.lower()}_{uid}",
                password="Test1234",
                role=User.Role.TEACHER,
            )
            assignment = SubjectAssignment.objects.create(
                school=self.school,
                academic_year=self.year,
                term=self.term,
                classroom=self.classroom,
                specialty=self.specialty,
                subject=subject,
            )
            assignment.teachers.add(teacher)
            self.subjects.append(subject)
            self.assignments.append(assignment)

        self.rooms = [
            Room.objects.create(
                school=self.school,
                name=f"Room {i}-{uid}",
                room_type="CLASSROOM",
                capacity=40,
            )
            for i in range(rooms)
        ]
        # Slots are school-scoped so a parallel school's periods cannot leak in.
        self.slots = []
        for day in range(days):
            for p in range(periods):
                hour = 8 + p
                self.slots.append(
                    TimeSlot.objects.create(
                        school=self.school,
                        day_of_week=day,
                        start_time=time(hour, 0),
                        end_time=time(hour + 1, 0),
                        slot_name=f"Period {p + 1}",
                        is_active=True,
                    )
                )
        # Canonical generator ordering.
        self.slots.sort(key=lambda s: (s.day_of_week, s.start_time, s.pk))

    def generate(self):
        return TimetableGenerator(self.year, self.term).generate_schedule(
            created_by=self.admin
        )


class PeriodsPerWeekTests(_GraphMixin, TestCase):
    """Acceptance 1 — 5 periods allocated produces 5 scheduled lessons."""

    def setUp(self):
        self.build(subject_names=("Math",), days=5, periods=2)

    def test_five_periods_per_week_produces_five_lessons(self):
        CurriculumAllocation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            subject=self.subjects[0],
            periods_per_week=5,
        )
        schedule = self.generate()

        entries = schedule.entries.filter(subject=self.subjects[0])
        self.assertEqual(
            entries.count(),
            5,
            "an allocation of 5 periods/week must yield 5 lessons; before item "
            "2.3 the generator placed exactly one and stopped",
        )
        # Five DISTINCT periods — not the same slot booked five times.
        self.assertEqual(len({e.time_slot_id for e in entries}), 5)
        # And still a legal timetable.
        self.assertEqual(evaluate_schedule(schedule)["hard_violations_total"], 0)

    def test_year_wide_allocation_applies_when_no_term_row_exists(self):
        CurriculumAllocation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=None,
            classroom=self.classroom,
            subject=self.subjects[0],
            periods_per_week=3,
        )
        schedule = self.generate()
        self.assertEqual(schedule.entries.count(), 3)

    def test_term_row_overrides_year_wide_row(self):
        CurriculumAllocation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=None,
            classroom=self.classroom,
            subject=self.subjects[0],
            periods_per_week=3,
        )
        CurriculumAllocation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            subject=self.subjects[0],
            periods_per_week=6,
        )
        index = build_allocation_index(self.year, self.term)
        spec = resolve_allocation(self.classroom.id, self.subjects[0].id, index)
        self.assertEqual(spec.periods_per_week, 6)
        self.assertEqual(spec.source, "term")
        self.assertEqual(self.generate().entries.count(), 6)


class BlockLengthTests(_GraphMixin, TestCase):
    """A double laboratory block is two ADJACENT periods on ONE day, one room."""

    def setUp(self):
        self.build(subject_names=("Science",), days=5, periods=2)

    def test_double_period_lands_adjacent_on_the_same_day_in_one_room(self):
        CurriculumAllocation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            subject=self.subjects[0],
            periods_per_week=2,
            block_length=2,
        )
        schedule = self.generate()
        entries = list(schedule.entries.select_related("time_slot").order_by("pk"))
        self.assertEqual(len(entries), 2)
        days = {e.time_slot.day_of_week for e in entries}
        self.assertEqual(len(days), 1, "a double period must not straddle two days")
        self.assertEqual(
            len({e.room_id for e in entries}),
            1,
            "both halves of a block must be in the same room",
        )
        starts = sorted(e.time_slot.start_time for e in entries)
        self.assertEqual([time(8, 0), time(9, 0)], starts)

    def test_remainder_is_placed_not_dropped(self):
        # 5 periods in blocks of 2 -> 2 + 2 + 1. Under-teaching by silently
        # dropping the remainder is the failure this asserts against.
        spec = AllocationSpec(periods_per_week=5, block_length=2)
        self.assertEqual(spec.blocks(), [2, 2, 1])


class CycleRotationTests(_GraphMixin, TestCase):
    """Acceptance 2 — a 2-week cycle produces a DIFFERENT week-B schedule."""

    def setUp(self):
        self.build(subject_names=("Math", "English"), days=5, periods=2)

    def test_two_week_cycle_week_b_differs_from_week_a(self):
        for subject in self.subjects:
            CurriculumAllocation.objects.create(
                school=self.school,
                academic_year=self.year,
                term=self.term,
                classroom=self.classroom,
                subject=subject,
                periods_per_week=1,
                cycle_length=2,
            )
        schedule = self.generate()

        week_a = {
            (e.subject_id, e.time_slot_id)
            for e in schedule.entries.filter(cycle_week=1)
        }
        week_b = {
            (e.subject_id, e.time_slot_id)
            for e in schedule.entries.filter(cycle_week=2)
        }
        self.assertEqual(len(week_a), 2, "week A must schedule both subjects")
        self.assertEqual(len(week_b), 2, "week B must schedule both subjects")
        self.assertNotEqual(
            week_a,
            week_b,
            "a 2-week rotation whose week B is a copy of week A is not a "
            "rotation — it is the same one-week timetable twice",
        )
        # Sharing a period across weeks is NOT a clash.
        self.assertEqual(evaluate_schedule(schedule)["hard_violations_total"], 0)

    def test_plan_cycle_is_the_longest_cycle_any_subject_asks_for(self):
        self.assertEqual(plan_cycle_length([]), 1)
        self.assertEqual(
            plan_cycle_length(
                [AllocationSpec(cycle_length=1), AllocationSpec(cycle_length=3)]
            ),
            3,
        )

    def test_weekly_subject_recurs_in_every_week_of_the_rotation(self):
        # Math rotates on 2 weeks; English is an ordinary weekly subject. A
        # weekly subject must appear in BOTH weeks, not only week A.
        CurriculumAllocation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            subject=self.subjects[0],
            periods_per_week=1,
            cycle_length=2,
        )
        schedule = self.generate()
        english = self.subjects[1]
        weeks = set(
            schedule.entries.filter(subject=english).values_list(
                "cycle_week", flat=True
            )
        )
        self.assertEqual(weeks, {1, 2})


class NoAllocationParityTests(_GraphMixin, TestCase):
    """Acceptance 4 — a tenant with no allocations gets its CURRENT timetable.

    The expected placement below is the pre-item-2.3 behaviour written out
    literally: walk (day_of_week, start_time) and give each demand the first
    slot its cohort is free for. If demand handling ever starts reordering or
    rotating the default case, this goes red — which is the point.
    """

    def setUp(self):
        self.build(subject_names=("Math", "English", "Science"), days=5, periods=2)

    def test_default_spec_is_one_period_one_block_one_week(self):
        self.assertEqual(DEFAULT_ALLOCATION.periods_per_week, 1)
        self.assertEqual(DEFAULT_ALLOCATION.block_length, 1)
        self.assertEqual(DEFAULT_ALLOCATION.cycle_length, 1)
        self.assertEqual(
            resolve_allocation(self.classroom.id, self.subjects[0].id, {}),
            DEFAULT_ALLOCATION,
        )

    def test_no_allocation_rows_reproduce_the_legacy_placement_exactly(self):
        self.assertEqual(CurriculumAllocation.objects.count(), 0)
        schedule = self.generate()

        entries = list(schedule.entries.order_by("pk"))
        self.assertEqual(len(entries), len(self.assignments))

        # Demands are consumed in SubjectAssignment's Meta ordering
        # (classroom name, specialty name, SUBJECT NAME) and each takes the
        # next slot its cohort is free for, walking (day_of_week, start_time).
        # One cohort + one specialty here, so that reduces to subject name.
        by_name = sorted(self.subjects, key=lambda s: s.name)
        expected = {
            by_name[i].id: self.slots[i].id for i in range(len(by_name))
        }
        actual = {e.subject_id: e.time_slot_id for e in entries}
        self.assertEqual(actual, expected)

        # And nothing entered the rotation.
        self.assertEqual({e.cycle_week for e in entries}, {1})
