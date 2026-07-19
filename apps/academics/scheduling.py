"""
Phase 9 Task 4: Advanced Scheduling System
Automated timetabling, room allocation, conflict detection

INTEGRATES WITH:
- apps.academics.models (Classroom, Subject, Teacher)
- apps.people.models (TeacherProfile)
- Existing classroom and subject infrastructure
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import List, Dict, Optional

User = get_user_model()


class Room(models.Model):
    """Physical classrooms and facilities"""

    ROOM_TYPES = [
        ("CLASSROOM", "Standard Classroom"),
        ("LAB", "Laboratory"),
        ("AUDITORIUM", "Auditorium"),
        ("GYM", "Gymnasium"),
        ("LIBRARY", "Library"),
        ("COMPUTER_LAB", "Computer Lab"),
    ]

    name = models.CharField(max_length=100, unique=True)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES)
    capacity = models.IntegerField()
    capacity_fraction = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1,
        help_text="Fractional utilization cap (1.00 = full room; 0.50 = half-day block).",
    )
    floor = models.IntegerField(default=1)
    building = models.CharField(max_length=100, blank=True)
    facilities = models.JSONField(
        default=list
    )  # ["projector", "whiteboard", "computers"]
    is_available = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Metric-15 (part B): links this academic Room to the schoolops booking system
    # (Metric #10 BookableResource) so a scheduled class and an ad-hoc room booking
    # cannot occupy the same room at the same wall-clock time. Nullable + optional so
    # unlinked rooms keep their prior behaviour (no cross-check). ``db_constraint=False``
    # keeps this a soft cross-app link (same convention as academics <-> people/schools
    # FKs in ``models_tenant_runtime.py``) so the two apps stay independently migratable.
    bookable_resource = models.ForeignKey(
        "schoolops.BookableResource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="academics_rooms",
        help_text=(
            "Optional link to the schoolops BookableResource this room maps to. When "
            "set, timetable generation AND publish cross-check scheduled classes "
            "against confirmed ad-hoc bookings of the resource."
        ),
    )

    class Meta:
        ordering = ["building", "floor", "name"]
        indexes = [
            models.Index(fields=["room_type", "is_available"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.room_type})"


class InstructionShift(models.Model):
    """School-day shift (e.g. Latin American turno) — partitions room/teacher booking."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="instruction_shifts",
    )
    code = models.SlugField(max_length=32)
    label = models.CharField(max_length=80)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["school_id", "sort_order", "code"]
        unique_together = [("school", "code")]
        verbose_name = "Instruction shift"
        verbose_name_plural = "Instruction shifts"

    def __str__(self):
        return f"{self.label} ({self.code})"


class TimeSlot(models.Model):
    """Predefined time slots for scheduling"""

    DAYS_OF_WEEK = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_name = models.CharField(max_length=50)  # "Period 1", "Morning Session"
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["day_of_week", "start_time"]
        unique_together = ("day_of_week", "start_time", "end_time")

    def __str__(self):
        return f"{self.get_day_of_week_display()} {self.slot_name} ({self.start_time}-{self.end_time})"

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError("Start time must be before end time")


class TeacherAvailability(models.Model):
    """Teacher availability preferences and constraints"""

    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="availability"
    )
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True)
    preference_level = models.IntegerField(
        default=5, help_text="1-10, higher is more preferred"
    )
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("teacher", "time_slot")
        verbose_name_plural = "Teacher Availabilities"

    def __str__(self):
        status = "Available" if self.is_available else "Unavailable"
        return f"{self.teacher.username} - {self.time_slot.slot_name}: {status}"


class Schedule(models.Model):
    """Master schedule for academic terms"""

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PUBLISHED", "Published"),
        ("ARCHIVED", "Archived"),
    ]

    name = models.CharField(max_length=255)
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.CASCADE
    )
    term = models.ForeignKey("academics.Term", on_delete=models.CASCADE)
    shift = models.ForeignKey(
        InstructionShift,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="schedules",
        help_text="When set, room conflicts apply within this shift only.",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    generated_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.name} - {self.term.name}"

    def publish(self):
        """Publish this plan as the term's live timetable.

        Demotes any rival published plan for the same (term, shift) back to DRAFT,
        because a term/shift has exactly ONE live timetable — two would mean the
        school is genuinely double-booking teachers and rooms.

        This invariant used to be an accident of the ScheduleEntry uniques being
        keyed on ``term``: they made a second plan of ANY status impossible, which
        blocked double-publishing only as a side effect of also blocking all
        re-planning. Those uniques are now per-plan (see ScheduleEntry.Meta), so
        the invariant is enforced here, where it is actually about publishing —
        and drafting a replacement no longer requires destroying the live one.
        """
        with transaction.atomic():
            # tenant-isolation-allow: schedule-publish-demote-rivals-scoped-by-term-and-shift-fks
            Schedule.objects.filter(
                term_id=self.term_id, shift_id=self.shift_id, status="PUBLISHED"
            ).exclude(pk=self.pk).update(status="DRAFT")
            self.status = "PUBLISHED"
            self.published_at = timezone.now()
            self.save()


class ScheduleEntry(models.Model):
    """Individual class session in a schedule"""

    schedule = models.ForeignKey(
        Schedule, on_delete=models.CASCADE, related_name="entries"
    )
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.CASCADE,
        related_name="schedule_entries",
        editable=False,
        help_text="Denormalized from schedule.term for DB conflict constraints.",
    )
    instruction_shift = models.ForeignKey(
        InstructionShift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_entries",
        editable=False,
        help_text="Denormalized from schedule.shift; NULL = term-wide booking scope.",
    )
    classroom = models.ForeignKey("academics.Classroom", on_delete=models.CASCADE)
    subject = models.ForeignKey("academics.Subject", on_delete=models.CASCADE)
    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="teaching_slots"
    )
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)

    # For handling conflicts/changes
    is_cancelled = models.BooleanField(default=False)
    replacement_teacher = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replacement_slots",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Schedule Entries"
        indexes = [
            models.Index(fields=["schedule", "time_slot"]),
            models.Index(fields=["teacher", "time_slot"]),
            models.Index(fields=["room", "time_slot"]),
            models.Index(fields=["term", "teacher", "time_slot"]),
            models.Index(fields=["term", "room", "time_slot"]),
        ]
        # Double-booking is prevented PER PLAN, not per term.
        #
        # Phase 4E (0055) keyed these on ``term``, which is the right intent at the
        # wrong scope: bookings live in a Schedule, and a term legitimately holds
        # MANY of them. ``generate_schedule`` mints a new DRAFT on every run,
        # ``solve_timetable`` does the same, Schedule carries DRAFT/PUBLISHED
        # statuses, and ``compare_schedules`` exists purely to weigh two candidate
        # plans for one term against each other. Term-scoping made the SECOND plan
        # for any term impossible: every entry collided with the first on
        # (term, teacher|room, time_slot) and died with IntegrityError, so a school
        # could generate its timetable exactly once, ever.
        #
        # That already burned the product once: the regenerate view now deletes
        # EVERY schedule for the term (see views_timetable + the
        # test_timetable_regenerate_after_publish regression) purely to dodge this
        # constraint — destroying the live published timetable to make room for an
        # unreviewed draft. Scoping to the plan removes the need for that trade.
        #
        # A draft is a proposal, not a commitment, so two plans proposing the same
        # teacher/slot is not a conflict. The real-world invariant — the LIVE
        # timetable never double-books — is preserved by these per-plan uniques
        # plus ``Schedule.publish``, which demotes any rival published plan for the
        # same (term, shift). ``instruction_shift`` is constant within a plan
        # (``_sync_scope_from_schedule`` copies it from the schedule), so the old
        # shift/term-wide split collapses to one constraint per resource.
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "teacher", "time_slot"],
                condition=models.Q(is_cancelled=False),
                name="uniq_schedentry_teacher_slot_in_plan",
            ),
            models.UniqueConstraint(
                fields=["schedule", "room", "time_slot"],
                condition=models.Q(is_cancelled=False),
                name="uniq_schedentry_room_slot_in_plan",
            ),
        ]

    def __str__(self):
        return (
            f"{self.classroom.name} - {self.subject.name} ({self.time_slot.slot_name})"
        )

    def _sync_scope_from_schedule(self) -> None:
        if not self.schedule_id:
            return
        self.term_id = self.schedule.term_id
        self.instruction_shift_id = self.schedule.shift_id

    def save(self, *args, **kwargs):
        self._sync_scope_from_schedule()
        super().save(*args, **kwargs)

    def clean(self):
        """Validate no conflicts (ORM layer; DB partial uniques enforce on save).

        Scoped to the PLAN, mirroring the per-plan uniques in Meta. It used to be
        term-scoped, which rejected any booking a RIVAL plan for the same term had
        already made — so this raised ValidationError on every entry of a second
        draft, blocking re-planning at the ORM layer exactly as the old DB
        constraints did at the storage layer. A rival draft is a proposal, not a
        clash.
        """
        if self.pk is None:
            self._sync_scope_from_schedule()
            if not self.schedule_id:
                return
            teacher_qs = ScheduleEntry.objects.filter(
                schedule_id=self.schedule_id,
                teacher=self.teacher,
                time_slot=self.time_slot,
                is_cancelled=False,
            )
            if teacher_qs.exists():
                raise ValidationError(
                    f"Teacher {self.teacher.username} is already scheduled for {self.time_slot.slot_name}"
                )

            room_qs = ScheduleEntry.objects.filter(
                schedule_id=self.schedule_id,
                room=self.room,
                time_slot=self.time_slot,
                is_cancelled=False,
            )
            if room_qs.exists():
                raise ValidationError(
                    f"Room {self.room.name} is already booked for {self.time_slot.slot_name}"
                )


class SchedulingConstraint(models.Model):
    """Custom scheduling rules and constraints"""

    CONSTRAINT_TYPES = [
        ("MAX_DAILY_LESSONS", "Maximum daily lessons per teacher"),
        ("MIN_BREAK_TIME", "Minimum break between lessons"),
        ("PREFERRED_ROOM", "Preferred room for subject"),
        ("NO_BACK_TO_BACK", "No back-to-back lessons for same class"),
        ("BLOCK_TIME", "Block specific time for activity"),
    ]

    name = models.CharField(max_length=255)
    constraint_type = models.CharField(max_length=30, choices=CONSTRAINT_TYPES)
    parameters = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(
        default=5, help_text="1-10, higher is more important"
    )

    class Meta:
        ordering = ["-priority", "name"]

    def __str__(self):
        return f"{self.name} ({self.constraint_type})"


class TimetableGenerator:
    """
    Automated timetable generation using constraint satisfaction

    INTEGRATES WITH existing models:
    - apps.academics.models.Classroom
    - apps.academics.models.Subject
    - apps.people.models.TeacherProfile
    """

    def __init__(self, academic_year, term):
        self.academic_year = academic_year
        self.term = term
        self.constraints = []
        self.schedule_entries = []

    def load_constraints(self):
        """Load active scheduling constraints"""
        self.constraints = SchedulingConstraint.objects.filter(is_active=True).order_by(
            "-priority"
        )

    def check_teacher_availability(self, teacher, time_slot) -> bool:
        """Check if teacher is available for time slot"""
        try:
            availability = TeacherAvailability.objects.get(
                teacher=teacher, time_slot=time_slot
            )
            return availability.is_available
        except TeacherAvailability.DoesNotExist:
            return True  # Assume available if not specified

    def check_room_availability(self, room, time_slot, schedule) -> bool:
        """Check if room is free of other schedule entries AND confirmed bookings.

        Metric 15 (solver-time #10 link): when ``room.bookable_resource`` is set,
        a CONFIRMED ``schoolops.ResourceBooking`` that overlaps any concrete
        occurrence of this weekly slot across the schedule's term makes the room
        unavailable for placement — so the generator never drafts a clash that
        publish would later refuse.
        """
        busy = ScheduleEntry.objects.filter(
            schedule=schedule, room=room, time_slot=time_slot, is_cancelled=False
        ).exists()
        if busy:
            return False
        term = getattr(schedule, "term", None) or self.term
        return not room_timeslot_conflicts_with_confirmed_bookings(
            room, time_slot, term
        )

    def find_suitable_room(
        self, classroom, subject, time_slot, schedule
    ) -> Optional[Room]:
        """Find best room for class based on capacity and facilities"""
        # Get student count for classroom
        student_count = (
            classroom.students.count() if hasattr(classroom, "students") else 30
        )

        # Find rooms with sufficient capacity (prefetch booking link for #10 check)
        suitable_rooms = Room.objects.filter(
            is_available=True, capacity__gte=student_count
        ).select_related("bookable_resource").order_by("capacity")

        # Check availability
        for room in suitable_rooms:
            if self.check_room_availability(room, time_slot, schedule):
                return room

        return None

    def generate_schedule(self, created_by) -> Schedule:
        """
        Generate optimized schedule for term

        Algorithm:
        1. Load all classrooms and subjects
        2. Load constraints and teacher availability
        3. Assign time slots using constraint satisfaction
        4. Allocate rooms based on capacity and availability
        5. Validate no conflicts
        """
        from apps.academics.models import SubjectAssignment

        self.load_constraints()

        # Create schedule (DRAFT — review + publish happen downstream).
        schedule = Schedule.objects.create(
            name=f"{self.term.name} Schedule",
            academic_year=self.academic_year,
            term=self.term,
            status="DRAFT",
            created_by=created_by,
        )

        # Active time slots, ordered so placement is deterministic.
        time_slots = list(
            TimeSlot.objects.filter(is_active=True).order_by(
                "day_of_week", "start_time"
            )
        )

        # Demands come from the real academic structure: one (classroom, subject,
        # teacher) per SubjectAssignment for this (year, term). The Subject model
        # carries no classroom/teacher FK — those live on SubjectAssignment /
        # TeacherAssignment — so the generator resolves them here, mirroring the
        # CP-SAT sibling in ``scheduling_solver._solve_with_ortools``.
        # tenant-isolation-allow: scoped via academic_year + term FKs (both tenant-bound)
        subject_assignments = (
            SubjectAssignment.objects.filter(
                academic_year=self.academic_year, term=self.term
            )
            .select_related("classroom", "subject")
            .prefetch_related("teachers")
        )

        for sa in subject_assignments:
            classroom = sa.classroom
            subject = sa.subject
            teacher = self._resolve_assignment_teacher(sa)
            if teacher is None:
                # Nobody to teach it — cannot book a class with no teacher.
                continue

            for time_slot in time_slots:
                # Respect stated teacher availability.
                if not self.check_teacher_availability(teacher, time_slot):
                    continue

                # Teacher already booked this slot in this draft?
                teacher_conflict = ScheduleEntry.objects.filter(
                    schedule=schedule,
                    teacher=teacher,
                    time_slot=time_slot,
                    is_cancelled=False,
                ).exists()
                if teacher_conflict:
                    continue

                # Cohort (classroom) already in another subject this slot? The DB
                # partial-unique constraints cover teacher+room but NOT the cohort,
                # so guard it here or evaluate_schedule reports a hard violation.
                cohort_conflict = ScheduleEntry.objects.filter(
                    schedule=schedule,
                    classroom=classroom,
                    time_slot=time_slot,
                    is_cancelled=False,
                ).exists()
                if cohort_conflict:
                    continue

                # Find suitable room (schedule-scoped availability check).
                room = self.find_suitable_room(
                    classroom, subject, time_slot, schedule
                )
                if room:
                    ScheduleEntry.objects.create(
                        schedule=schedule,
                        classroom=classroom,
                        subject=subject,
                        teacher=teacher,
                        room=room,
                        time_slot=time_slot,
                    )
                    break  # Move to next demand.

        return schedule

    def _resolve_assignment_teacher(self, subject_assignment):
        """Resolve the teaching ``User`` for a SubjectAssignment.

        Prefers the canonical ``TeacherAssignment`` (evals) link — the same source
        the CP-SAT solver uses — then falls back to the assignment's ``teachers``
        M2M. Returns a ``User`` or ``None`` when no teacher is linked.
        """
        try:
            from apps.evals.models import TeacherAssignment

            ta = (
                # tenant-isolation-allow: scoped-via-subject-assignment-fk-which-is-school-scoped
                TeacherAssignment.objects.filter(
                    subject_assignment=subject_assignment, is_active=True
                )
                .select_related("teacher__user")
                .first()
            )
            if ta and ta.teacher and getattr(ta.teacher, "user", None):
                return ta.teacher.user
        except ImportError:
            pass
        return subject_assignment.teachers.first()

    def detect_conflicts(self, schedule) -> List[Dict]:
        """Detect scheduling conflicts in a plan.

        The teacher and room checks are now defense-in-depth: the per-plan DB
        uniques (see ScheduleEntry.Meta) make those two classes unstorable, so
        they can only fire if a constraint is ever dropped or data is loaded
        around the ORM. Cheap to keep, and they fail loudly rather than silently.

        The CLASSROOM check is not redundant — it is the only guard that exists.
        A ``Classroom`` here is the student GROUP (Form 1, Class A), not the room,
        and nothing prevents booking one group into two lessons at the same time.
        That is the conflict that matters most (students cannot be in two places
        at once) and it had no DB constraint AND no detector, so the operator
        conflicts endpoint (api_views) reported a clean plan while a class sat
        double-booked. ``scheduling_evaluation._hard_violations`` counts it, but
        nothing surfaced it here.
        """
        conflicts = []

        entries = ScheduleEntry.objects.filter(schedule=schedule, is_cancelled=False)

        # Check for classroom (student group) double-booking — the real gap.
        for entry in entries:
            overlaps = entries.filter(
                classroom=entry.classroom, time_slot=entry.time_slot
            ).exclude(pk=entry.pk)

            if overlaps.exists():
                conflicts.append(
                    {
                        "type": "CLASSROOM_CONFLICT",
                        "classroom": entry.classroom.name,
                        "time_slot": str(entry.time_slot),
                        "entries": [entry.pk]
                        + list(overlaps.values_list("pk", flat=True)),
                    }
                )

        # Check for teacher double-booking
        for entry in entries:
            overlaps = entries.filter(
                teacher=entry.teacher, time_slot=entry.time_slot
            ).exclude(pk=entry.pk)

            if overlaps.exists():
                conflicts.append(
                    {
                        "type": "TEACHER_CONFLICT",
                        "teacher": entry.teacher.username,
                        "time_slot": str(entry.time_slot),
                        "entries": [entry.pk]
                        + list(overlaps.values_list("pk", flat=True)),
                    }
                )

        # Check for room double-booking
        for entry in entries:
            overlaps = entries.filter(
                room=entry.room, time_slot=entry.time_slot
            ).exclude(pk=entry.pk)

            if overlaps.exists():
                conflicts.append(
                    {
                        "type": "ROOM_CONFLICT",
                        "room": entry.room.name,
                        "time_slot": str(entry.time_slot),
                        "entries": [entry.pk]
                        + list(overlaps.values_list("pk", flat=True)),
                    }
                )

        return conflicts

    def optimize_schedule(self, schedule):
        """
        Optimize schedule based on preferences and constraints

        Optimization goals:
        - Minimize teacher travel between rooms
        - Balance workload across days
        - Respect teacher preferences
        - Minimize gaps in student schedules
        """
        entries = ScheduleEntry.objects.filter(
            schedule=schedule, is_cancelled=False
        ).select_related("teacher", "room", "time_slot")

        # Calculate teacher workload per day
        teacher_workload = {}
        for entry in entries:
            day = entry.time_slot.day_of_week
            teacher_id = entry.teacher.id

            key = (teacher_id, day)
            teacher_workload[key] = teacher_workload.get(key, 0) + 1

        # Redistribute: for teachers with >6 classes on a day, move entries to lighter days (same time, different day).
        # Tracked: WHAT_IS_LEFT_MASTER.md O9/O63 — implementation complete; optional future: configurable max per day, room preferences.
        overloaded = [(tid, d) for (tid, d), c in teacher_workload.items() if c > 6]
        for teacher_id, from_day in overloaded:
            day_entries = [
                e
                for e in entries
                if e.teacher_id == teacher_id and e.time_slot.day_of_week == from_day
            ]
            if not day_entries:
                continue
            # Find another day with same start_time/end_time where this teacher has fewer classes
            for entry in day_entries[
                :2
            ]:  # Move at most 2 per teacher-day to avoid thrashing
                slot = entry.time_slot
                candidates = list(
                    TimeSlot.objects.filter(
                        is_active=True,
                        start_time=slot.start_time,
                        end_time=slot.end_time,
                    )
                    .exclude(day_of_week=from_day)
                    .order_by("day_of_week")
                )
                for target_slot in candidates:
                    target_day = target_slot.day_of_week
                    target_count = teacher_workload.get((teacher_id, target_day), 0)
                    if target_count >= 6:
                        continue
                    # Check room free on target_slot
                    if ScheduleEntry.objects.filter(
                        schedule=schedule,
                        room=entry.room,
                        time_slot=target_slot,
                        is_cancelled=False,
                    ).exists():
                        continue
                    # Move entry to target_slot
                    entry.time_slot = target_slot
                    entry.save()
                    teacher_workload[(teacher_id, from_day)] = (
                        teacher_workload.get((teacher_id, from_day), 0) - 1
                    )
                    teacher_workload[(teacher_id, target_day)] = target_count + 1
                    break

        return schedule


# API alias used by views_v1 and api_views
ScheduleGenerator = TimetableGenerator


# ---------------------------------------------------------------------------
# Metric-15 (part B): scheduling <-> booking (#10) room-vs-time cross-check.
#
# A ``ScheduleEntry`` books a ``Room`` in a WEEKLY ``TimeSlot`` (day-of-week +
# start/end time) for a whole ``Term``. A ``schoolops.ResourceBooking`` books a
# ``BookableResource`` for a CONCRETE wall-clock ``time_range``. When a Room is
# linked to a BookableResource (``Room.bookable_resource``), the two must not
# collide: a scheduled class and a confirmed ad-hoc booking cannot own the same
# room at the same real time.
#
# Two enforcement layers:
#   1. Solver-time — ``TimetableGenerator.check_room_availability`` calls
#      ``room_timeslot_conflicts_with_confirmed_bookings`` so DRAFT schedules are
#      never placed into a known booking clash.
#   2. Publish-time — ``find_schedule_booking_conflicts`` refuses publish if any
#      entry still overlaps (defense-in-depth for hand-edited drafts).
#
# Both expand each linked entry's weekly slot into concrete occurrences across
# the term and use half-open interval overlap in Python — no btree_gist / range
# operators — so they run identically on SQLite and Postgres. On SQLite
# ``DateTimeRangeField`` has no ``from_db_value`` and round-trips as its canonical
# text ``'[lower,upper)'``, so ``_booking_bounds`` parses that text; on Postgres
# the value is a ``Range`` whose ``.lower``/``.upper`` are datetimes.
# ---------------------------------------------------------------------------

_CONFIRMED_STATUS = "confirmed"


def _aware(dt: datetime) -> datetime:
    """Make a naive datetime tz-aware under ``USE_TZ`` (pass-through otherwise)."""
    if getattr(settings, "USE_TZ", False) and timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_range_text(text: str):
    """Parse a Postgres range literal ``'[lower,upper)'`` into ``(lower, upper)``.

    Used on SQLite, where ``DateTimeRangeField`` has no ``from_db_value`` and the
    column round-trips as its canonical text form. Returns a ``(datetime|None,
    datetime|None)`` tuple, or ``None`` for an empty/unparseable range.
    """
    s = (text or "").strip()
    if not s or "empty" in s.lower():
        return None
    if s[0] in "[(" and s[-1] in ")]":
        s = s[1:-1]
    if "," not in s:
        return None
    lo_str, hi_str = s.split(",", 1)

    def _p(raw: str):
        raw = raw.strip().strip('"')
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    return (_p(lo_str), _p(hi_str))


def _booking_bounds(value):
    """Return ``(lower, upper)`` datetimes for a booking ``time_range`` value.

    Backend-portable: a ``Range`` on Postgres (read ``.lower``/``.upper``), the
    canonical text ``'[lower,upper)'`` on SQLite (parse it). ``None`` when unusable.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return _parse_range_text(value)
    return (getattr(value, "lower", None), getattr(value, "upper", None))


def _confirmed_booking_intervals(resource) -> list:
    """All confirmed booking intervals for one resource as aware ``(lower, upper,
    title, id)`` tuples. School-scoped via the resource's own ``school_id``."""
    from apps.schoolops.models_resource_booking import ResourceBooking

    # tenant-isolation-allow: scoped-via-resource-school-id-which-is-tenant-bound
    qs = ResourceBooking.objects.filter(
        school_id=resource.school_id,
        resource_id=resource.id,
        status=_CONFIRMED_STATUS,
    ).only("id", "title", "time_range")

    intervals = []
    for booking in qs.iterator():
        bounds = _booking_bounds(booking.time_range)
        if not bounds:
            continue
        lower, upper = bounds
        if lower is None or upper is None:
            continue
        intervals.append((_aware(lower), _aware(upper), booking.title, booking.id))
    return intervals


def _slot_occurrences(term_start, term_end, day_of_week, start_time, end_time):
    """Yield concrete ``(start_dt, end_dt)`` occurrences of a weekly slot across a
    term. One per week: the first ``day_of_week`` on/after ``term_start``, then a
    7-day stride through ``term_end`` (inclusive). ``day_of_week`` follows
    ``TimeSlot`` / Python ``date.weekday()`` (0=Monday)."""
    if term_start is None or term_end is None:
        return
    offset = (day_of_week - term_start.weekday()) % 7
    day = term_start + timedelta(days=offset)
    while day <= term_end:
        yield (
            datetime.combine(day, start_time),
            datetime.combine(day, end_time),
        )
        day += timedelta(days=7)


def room_timeslot_conflicts_with_confirmed_bookings(room, time_slot, term) -> bool:
    """True when placing ``room`` at weekly ``time_slot`` for ``term`` would overlap
    a CONFIRMED schoolops booking on the room's linked ``BookableResource``.

    Used by the timetable generator (solver-time #10 respect) so DRAFT schedules
    are not emitted into known booking clashes. Rooms without
    ``bookable_resource`` never conflict here (publish-time back-compat).
    """
    resource = getattr(room, "bookable_resource", None)
    if resource is None:
        return False
    term_start = getattr(term, "start_date", None)
    term_end = getattr(term, "end_date", None)
    if term_start is None or term_end is None:
        return False
    if time_slot is None:
        return False

    booking_intervals = _confirmed_booking_intervals(resource)
    if not booking_intervals:
        return False

    for occ_start, occ_end in _slot_occurrences(
        term_start,
        term_end,
        time_slot.day_of_week,
        time_slot.start_time,
        time_slot.end_time,
    ):
        occ_start = _aware(occ_start)
        occ_end = _aware(occ_end)
        for lower, upper, _title, _booking_id in booking_intervals:
            if occ_start < upper and occ_end > lower:
                return True
    return False


def find_schedule_booking_conflicts(schedule) -> List[Dict]:
    """Room-vs-booking conflicts for a schedule (see module section above).

    For every non-cancelled ``ScheduleEntry`` whose ``room.bookable_resource`` is
    set, expand its weekly slot across the term and look for any CONFIRMED
    ``ResourceBooking`` on that resource whose interval overlaps an occurrence.

    Returns a list of conflict dicts (``room``, ``resource``, ``slot``,
    ``occurrence_start``/``occurrence_end``, ``booking_title``, ``booking_id``,
    ``entry_id``) — at most one per entry (the first overlapping occurrence).
    Empty list => no room-vs-booking clash. Pure read; no DB writes.
    """
    term = getattr(schedule, "term", None)
    term_start = getattr(term, "start_date", None)
    term_end = getattr(term, "end_date", None)
    if term_start is None or term_end is None:
        # Cannot expand a weekly slot into concrete datetimes without term bounds.
        return []

    entries = list(
        # tenant-isolation-allow: scoped-via-parent-schedule-which-is-school-scoped
        ScheduleEntry.objects.filter(
            schedule=schedule,
            is_cancelled=False,
            room__bookable_resource__isnull=False,
        ).select_related("room", "room__bookable_resource", "time_slot")
    )
    if not entries:
        return []

    school_id = getattr(schedule.academic_year, "school_id", None)
    intervals_cache: Dict[int, list] = {}
    conflicts: List[Dict] = []

    for entry in entries:
        resource = entry.room.bookable_resource
        # Isolation: only cross-check bookings owned by this schedule's school.
        if school_id is not None and resource.school_id != school_id:
            continue
        if resource.id not in intervals_cache:
            intervals_cache[resource.id] = _confirmed_booking_intervals(resource)
        booking_intervals = intervals_cache[resource.id]
        if not booking_intervals:
            continue

        slot = entry.time_slot
        hit = None
        for occ_start, occ_end in _slot_occurrences(
            term_start, term_end, slot.day_of_week, slot.start_time, slot.end_time
        ):
            occ_start = _aware(occ_start)
            occ_end = _aware(occ_end)
            for lower, upper, title, booking_id in booking_intervals:
                # Half-open overlap, matching booking_services.overlapping_confirmed_count.
                if occ_start < upper and occ_end > lower:
                    hit = (occ_start, occ_end, title, booking_id)
                    break
            if hit:
                break

        if hit:
            occ_start, occ_end, title, booking_id = hit
            conflicts.append(
                {
                    "room": entry.room.name,
                    "resource": resource.name,
                    "slot": str(slot),
                    "occurrence_start": occ_start,
                    "occurrence_end": occ_end,
                    "booking_title": title,
                    "booking_id": booking_id,
                    "entry_id": entry.pk,
                }
            )

    return conflicts
