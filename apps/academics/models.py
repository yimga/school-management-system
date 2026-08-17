from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError


def _default_currency():
    """Platform default currency (no hardcoded XAF). See config.PLATFORM_DEFAULT_CURRENCY."""
    return getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD")


class AcademicYear(models.Model):
    # Phase 4: Enable audit logging for this model
    audit_enabled = True

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="academic_years",
    )
    name = models.CharField(max_length=50)  # e.g. "2025/2026"
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    is_locked = models.BooleanField(
        default=False,
        help_text="When set, no further grade edits or rollover from this year (year-end lock).",
    )
    enable_gce_registration = models.BooleanField(
        default=False,
        help_text="Enable the GCE/certification registration workflow for this academic year.",
    )
    # Edge<->cloud bidirectional sync (Phase 3): change cursor + offline-insert anchor.
    # null/blank so the additive migration needs no one-off default on existing rows.
    updated_at = models.DateTimeField(auto_now=True, null=True)
    client_offline_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    def __init__(self, *args, **kwargs):
        # Backwards-compatibility: accept `starts_on`/`ends_on` kwargs used by older code/tests
        if "starts_on" in kwargs:
            kwargs["start_date"] = kwargs.pop("starts_on")
        if "ends_on" in kwargs:
            kwargs["end_date"] = kwargs.pop("ends_on")
        super().__init__(*args, **kwargs)

    @property
    def starts_on(self):
        return self.start_date

    @property
    def ends_on(self):
        return self.end_date

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_academicyear_school_offline_id",
            ),
        ]

    def __str__(self):
        return self.name

    def format_start_date_display(self) -> str:
        """Gregorian + optional secondary calendar annotation for tenant region."""
        from apps.platform_runtime.calendar_display import format_dual_calendar_date

        return format_dual_calendar_date(self.start_date, school=self.school)

    def format_end_date_display(self) -> str:
        from apps.platform_runtime.calendar_display import format_dual_calendar_date

        return format_dual_calendar_date(self.end_date, school=self.school)


class Term(models.Model):
    # Backwards-compatible symbolic constants (no longer enforced as choices)
    class Name(models.TextChoices):
        FIRST = "FIRST", "First"
        SECOND = "SECOND", "Second"
        THIRD = "THIRD", "Third"

    # Phase 4: Enable audit logging for this model
    audit_enabled = True

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="terms",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="terms"
    )
    # Code identifier (free text, e.g., "FIRST", "SEM1", "Q1"). No choices to enable flexibility.
    name = models.CharField(max_length=20)
    # Optional custom label for flexible naming (e.g., "Semester 1").
    custom_label = models.CharField(max_length=30, blank=True)
    # Position within the academic year (1..4) to support 2–4 terms configuration.
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    # Edge<->cloud bidirectional sync (Phase 3): change cursor + offline-insert anchor.
    updated_at = models.DateTimeField(auto_now=True, null=True)
    client_offline_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    def __init__(self, *args, **kwargs):
        # Backwards-compatibility: accept keyword 'order' used by older code/tests
        if "order" in kwargs:
            kwargs["position"] = kwargs.pop("order")
        super().__init__(*args, **kwargs)

    @property
    def order(self):
        return self.position

    class Meta:
        unique_together = ("academic_year", "name")
        ordering = ["start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "position"],
                name="unique_term_position_per_year",
                condition=Q(position__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["academic_year", "custom_label"],
                name="unique_term_custom_label_per_year",
                condition=~Q(custom_label=""),
            ),
            models.CheckConstraint(
                # Local-first: allow 1–12 terms/periods, not a hardcoded max of 4. Aligns
                # with RegionConfig.term_count_per_year (1–12) so 2-semester, trimester,
                # quarter, and 5+-period/modular calendars are all valid. Terms beyond the
                # named choices use custom_label for their display name.
                check=(
                    Q(position__isnull=True) | (Q(position__gte=1) & Q(position__lte=12))
                ),
                name="term_position_range_1_12_or_null",
            ),
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~Q(client_offline_id=""),
                name="uniq_term_school_offline_id",
            ),
        ]

    def clean(self):
        super().clean()
        if self.position is not None and not (1 <= int(self.position) <= 12):
            raise ValidationError({"position": "Position must be between 1 and 12."})

    def __str__(self):
        return f"{self.academic_year} - {self.label}"

    @property
    def label(self) -> str:
        """Return display label, preferring custom_label if set."""
        return self.custom_label or self.get_name_display()

    # Backwards compatibility for existing code/templates calling get_name_display()
    def get_name_display(self) -> str:  # type: ignore[override]
        return self.custom_label or (self.name or "")


class Department(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="departments",
    )
    name = models.CharField(max_length=120)
    # Per-SCHOOL unique, not globally unique. A globally-unique code cannot be
    # bidirectionally synced on a shared cloud: a box creating a department whose code
    # already exists for ANOTHER tenant would collide. Scoping uniqueness to (school, code)
    # is a strict LOOSENING of the old global constraint (existing globally-unique rows all
    # satisfy it), and every production lookup is already school-scoped. See Meta.constraints.
    code = models.CharField(max_length=30)
    # Edge<->cloud bidirectional sync (Phase 3): change cursor + offline-insert anchor.
    updated_at = models.DateTimeField(auto_now=True, null=True)
    client_offline_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_department_school_offline_id",
            ),
            models.UniqueConstraint(
                fields=["school", "code"],
                name="uniq_department_school_code",
            ),
        ]

    def __str__(self):
        return self.name


class Specialty(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="specialties",
    )
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="specialties"
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, unique=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    # Client-generated id for a specialty created offline on an edge box; lets the
    # operator upsert it by (school, client_offline_id) on sync without pk collisions.
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Specialty"
        verbose_name_plural = "Specialties"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_specialty_school_offline_id",
            ),
        ]

    def __str__(self):
        return self.name


class Classroom(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="classrooms",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="classrooms"
    )
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="classrooms"
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, unique=True)
    allows_third_term = models.BooleanField(
        default=True,
        help_text="Disable to block third-term activities (e.g., Form 5/Upper Sixth).",
    )
    gce_eligible = models.BooleanField(
        default=False,
        help_text="When True, students in this class can be registered as GCE/certification candidates (e.g. Form 5, Upper Sixth). Form 4 and other non-exam classes should leave this unchecked.",
    )
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-classroom configuration. Honoured keys: `terminology` — "
            "classroom-scoped lexicon overrides in the same shape as "
            "`School.settings['terminology']`. Most-specific layer in the "
            "lexicon cascade (overrides school and ancestor layers)."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)
    # Client-generated id for a classroom created offline on an edge box; lets the
    # operator upsert it by (school, client_offline_id) on sync without pk collisions.
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_classroom_school_offline_id",
            ),
        ]

    def __str__(self):
        return self.name


class ClassroomPromotionMapping(models.Model):
    """
    Maps a classroom in the source year to the suggested classroom in the target year
    for rollover (e.g. Form 5A in 2024/25 → Lower Sixth A in 2025/26).
    Used by the year-end rollover wizard to suggest "next class".
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="classroom_promotion_mappings",
    )
    source_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="promotion_mappings_from"
    )
    source_classroom = models.ForeignKey(
        Classroom, on_delete=models.CASCADE, related_name="promotion_mappings_from"
    )
    target_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="promotion_mappings_to"
    )
    target_classroom = models.ForeignKey(
        Classroom, on_delete=models.CASCADE, related_name="promotion_mappings_to"
    )

    class Meta:
        unique_together = ("source_year", "source_classroom", "target_year")
        ordering = ["source_year", "source_classroom"]

    def __str__(self):
        return f"{self.source_classroom.name} ({self.source_year}) → {self.target_classroom.name} ({self.target_year})"


class Subject(models.Model):
    class Category(models.TextChoices):
        GENERAL = "GENERAL", "General"
        PROFESSIONAL = "PROFESSIONAL", "Professional"
        RELATED = "RELATED", "Related"
        OTHER = "OTHER", "Other"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subjects",
    )
    name = models.CharField(max_length=120)
    code = models.CharField(
        max_length=30,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "Optional national/country-standard subject code (e.g. a GCE board "
            "code). Auto-derived from the country subject-code scheme on seed and "
            "fully admin-editable; blank is allowed."
        ),
    )
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.OTHER
    )
    credits = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional: credit units for Higher Ed degree audit (e.g. 3.0).",
    )
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    # Client-generated id for a subject created offline on an edge box; lets the
    # operator upsert it by (school, client_offline_id) on sync without pk collisions.
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"],
                name="academics_subject_school_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_subject_school_offline_id",
            ),
        ]

    def __str__(self):
        return self.name


class SubjectAssignment(models.Model):
    """
    Connects:
    AcademicYear + Term + Classroom + Specialty + Subject + Coefficient
    This is what teachers get assigned to, and what evaluations (marks) point to later.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subject_assignments",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="subject_assignments"
    )
    term = models.ForeignKey(
        Term, on_delete=models.PROTECT, related_name="subject_assignments"
    )
    classroom = models.ForeignKey(
        Classroom, on_delete=models.PROTECT, related_name="subject_assignments"
    )
    specialty = models.ForeignKey(
        Specialty, on_delete=models.PROTECT, related_name="subject_assignments"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT, related_name="subject_assignments"
    )
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    grading_deadline_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional deadline for completing grades for this assignment (term/class/subject).",
    )
    teachers = models.ManyToManyField(
        "accounts.User",
        blank=True,
        related_name="taught_subject_assignments",
        help_text="Users (with TeacherProfile) responsible for teaching this assignment slot.",
    )

    class Meta:
        unique_together = ("academic_year", "term", "classroom", "specialty", "subject")
        ordering = ["classroom__name", "specialty__name", "subject__name"]

    def __str__(self):
        return f"{self.academic_year} | {self.term.label} | {self.classroom} | {self.specialty} | {self.subject} (coef {self.coefficient})"

    def clean(self):
        if self.term and self.classroom:
            if (self.term.position == 3) and not self.classroom.allows_third_term:
                raise ValidationError("Third term is not allowed for this classroom.")


class SpecialtySubject(models.Model):
    """The curriculum link — which subjects belong to a specialty (course of study).

    The platform had NO specialty↔subject relationship: ``Subject`` floated free,
    joined to a specialty only per-``SubjectAssignment`` slot. That left two gaps:
    a migrated teacher roster's subject id-lists could not be turned into
    assignments (which specialty owns a subject was unknowable), and the teaching
    grid could only be built under the single "General" specialty — so a student
    on a TVET trade had no gradeable assignments and no report card.

    This is a lightweight, admin-editable curriculum: a specialty's set of
    subjects, with an optional coefficient (the francophone weighted-average
    systems need per-subject coefficients). Seeded with a permissive default (all
    subjects for each specialty) that the admin trims per trade; the teaching-grid
    and teacher-assignment builders read it, falling back to "all subjects" when a
    specialty has no explicit curriculum yet."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="specialty_subjects",
    )
    specialty = models.ForeignKey(
        Specialty, on_delete=models.CASCADE, related_name="subject_links"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="specialty_links"
    )
    coefficient = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        help_text="Weight of this subject in the specialty's average (coefficient systems).",
    )
    is_core = models.BooleanField(
        default=True, help_text="Core (vs elective) subject for this specialty."
    )
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    # Client-generated id for a curriculum link created offline on an edge box; lets
    # the operator upsert it by (school, client_offline_id) on sync without pk collisions.
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["specialty", "subject"],
                name="academics_specialtysubject_uniq",
            ),
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_specialtysubject_school_offline_id",
            ),
        ]
        ordering = ["specialty__name", "subject__name"]

    def __str__(self):
        return f"{self.specialty} · {self.subject} (coef {self.coefficient})"


class CurriculumAllocation(models.Model):
    """How much weekly teaching time a class owes a subject.

    Item 2.3 of ``docs/PLATFORM_GLOBALIZATION_PROGRAM.md``.

    Before this model the timetable generator derived demand as "one
    ``SubjectAssignment`` == one lesson" (see the pre-change body of
    ``apps.academics.scheduling.TimetableGenerator.generate_schedule``, which
    ``break``-ed out of the slot loop after placing a single entry). Every
    subject therefore got exactly ONE period a week, which cannot express
    Maths five times weekly, a double laboratory block, or a two-week
    rotating cycle — i.e. most of the world's timetables.

    THREE INDEPENDENT KNOBS, deliberately not collapsed into one:

    ``periods_per_week``
        Lessons this class gets in EACH week of the cycle. Total lessons per
        cycle is ``periods_per_week * cycle_length``.
    ``block_length``
        Consecutive periods per teaching block. ``2`` is a double lab: two
        adjacent slots on the same day booked together. When
        ``periods_per_week`` is not a multiple of ``block_length`` the
        remainder is placed as a shorter trailing block rather than dropped.
    ``cycle_length``
        Number of weeks before the timetable repeats. ``1`` is the ordinary
        one-week timetable; ``2`` is the UK/IE/AU "week A / week B" rotation.
        Each cycle week is scheduled independently, so week B genuinely
        differs from week A instead of being a copy.

    SCOPE AND FALLBACK. ``term`` is nullable: a row with ``term=NULL`` is the
    year-wide allocation for that (classroom, subject), and a row naming a
    term overrides it for that term only. When NO row matches, the resolver
    returns ``DEFAULT_ALLOCATION`` (1 period/week, block 1, cycle 1) — which
    reproduces the pre-2.3 behaviour exactly, so a tenant that never creates
    an allocation gets the timetable it has today.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="curriculum_allocations",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="curriculum_allocations",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="curriculum_allocations",
        help_text="Leave empty to apply to every term of the year.",
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="curriculum_allocations",
        help_text="The class / section this allocation is for.",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="curriculum_allocations",
    )
    periods_per_week = models.PositiveSmallIntegerField(
        default=1,
        help_text="Lessons per week of the cycle. 5 = Maths every weekday.",
    )
    block_length = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Consecutive periods per teaching block. 2 = double period "
            "(e.g. a laboratory session)."
        ),
    )
    cycle_length = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Weeks before the timetable repeats. 1 = ordinary weekly "
            "timetable; 2 = week A / week B rotation."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["classroom__name", "subject__name"]
        verbose_name = "Curriculum allocation"
        verbose_name_plural = "Curriculum allocations"
        indexes = [
            models.Index(fields=["academic_year", "term", "classroom"]),
        ]
        constraints = [
            # Two PARTIAL uniques rather than one four-column unique_together:
            # ``term`` is nullable and NULL never equals NULL in SQL, so a
            # plain unique would silently permit unlimited duplicate
            # year-wide rows — the resolver would then pick arbitrarily.
            models.UniqueConstraint(
                fields=["academic_year", "term", "classroom", "subject"],
                condition=Q(term__isnull=False),
                name="academics_curralloc_term_scoped_uniq",
            ),
            models.UniqueConstraint(
                fields=["academic_year", "classroom", "subject"],
                condition=Q(term__isnull=True),
                name="academics_curralloc_year_scoped_uniq",
            ),
            models.CheckConstraint(
                check=Q(periods_per_week__gte=1),
                name="academics_curralloc_ppw_min_1",
            ),
            models.CheckConstraint(
                check=Q(block_length__gte=1),
                name="academics_curralloc_block_min_1",
            ),
            models.CheckConstraint(
                check=Q(cycle_length__gte=1),
                name="academics_curralloc_cycle_min_1",
            ),
        ]

    def __str__(self):
        base = f"{self.classroom} / {self.subject}: {self.periods_per_week}p/wk"
        if self.block_length > 1:
            base += f" x{self.block_length}"
        if self.cycle_length > 1:
            base += f" ({self.cycle_length}-week cycle)"
        return base

    def clean(self):
        if self.block_length and self.periods_per_week:
            if self.block_length > self.periods_per_week:
                raise ValidationError(
                    "block_length cannot exceed periods_per_week — a block "
                    "longer than the weekly allocation can never be placed."
                )
        if self.term_id and self.academic_year_id:
            if self.term.academic_year_id != self.academic_year_id:
                raise ValidationError(
                    "term must belong to the allocation's academic_year."
                )

    def save(self, *args, **kwargs):
        # Keep the tenant column in step with the academic graph so RLS-mode
        # deployments (USE_DJANGO_TENANTS=0) can filter on school_id. Mirrors
        # the nullable-school pattern used by Subject/SubjectAssignment.
        if self.school_id is None and self.academic_year_id:
            self.school_id = self.academic_year.school_id
        super().save(*args, **kwargs)


class CertificationExamSession(models.Model):
    """Certification registration window/session (GCE, OBC, etc)."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="certification_sessions",
    )

    class Board(models.TextChoices):
        GCE_BOARD = "GCE_BOARD", "GCE Board (Cameroon)"
        OBC = "OBC", "Office du Baccalauréat du Cameroun (OBC)"
        WAEC = "WAEC", "WAEC (West Africa)"
        NECO = "NECO", "NECO (Nigeria)"
        KCSE = "KCSE", "KCSE (Kenya)"
        IGCSE_CIE = "IGCSE_CIE", "Cambridge IGCSE"
        IB = "IB", "International Baccalaureate (IB)"
        AP_CB = "AP_CB", "College Board (AP/SAT)"
        BAC_FR = "BAC_FR", "Baccalauréat (France)"
        ABITUR_DE = "ABITUR_DE", "Abitur (Germany)"
        STATE_BOARD = "STATE_BOARD", "State/Provincial Board"
        OTHER = "OTHER", "Other"

    class Level(models.TextChoices):
        O_LEVEL = "O_LEVEL", "O-Level / IGCSE"
        A_LEVEL = "A_LEVEL", "A-Level / Advanced"
        TECHNICAL = "TECHNICAL", "Technical / Vocational"
        DIPLOMA = "DIPLOMA", "Diploma"
        OTHER = "OTHER", "Other"

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="certification_sessions"
    )
    # Optional: tie a session to a preset (rules, fees, document checklist).
    preset = models.ForeignKey(
        "academics.CertificationExamPreset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        help_text="Optional preset to standardize rules/fees/docs for this session.",
    )
    fee_template = models.ForeignKey(
        "academics.CertificationFeeTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        help_text="Optional fee template for this session (overrides preset default if set).",
    )
    document_checklist = models.ForeignKey(
        "academics.CertificationDocumentChecklist",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        help_text="Optional document checklist for this session (overrides preset default if set).",
    )
    board = models.CharField(
        max_length=20, choices=Board.choices, default=Board.OTHER
    )
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.OTHER)
    name = models.CharField(
        max_length=120,
        help_text="e.g., 'GCE Registration 2026 - O Level', 'IGCSE May/June 2026', 'WAEC SSCE 2026'",
    )
    exam_centre_name = models.CharField(max_length=200, blank=True)
    exam_centre_number = models.CharField(
        max_length=40,
        blank=True,
        help_text="Official centre number used by the board portal.",
    )
    contact_phone = models.CharField(max_length=60, blank=True)
    contact_email = models.EmailField(blank=True)

    registration_opens_at = models.DateTimeField(null=True, blank=True)
    registration_closes_at = models.DateTimeField(null=True, blank=True)
    ca_submission_deadline_at = models.DateTimeField(null=True, blank=True)

    # Admin override tracking (JSON: {"registration_locked_override": {"by": user_id, "at": timestamp, "reason": str}, ...})
    admin_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text="Admin override records for deadline bypasses (audit trail).",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("academic_year", "board", "level", "name")

    def __str__(self):
        return f"{self.name} ({self.academic_year})"

    def is_registration_open(self, now=None):
        """Check if registration window is currently open."""
        if now is None:
            from django.utils import timezone

            now = timezone.now()
        if self.registration_opens_at and now < self.registration_opens_at:
            return False
        if self.registration_closes_at and now > self.registration_closes_at:
            return False
        return True

    def is_registration_locked(self, now=None):
        """Check if registration is locked (closed or not yet open)."""
        return not self.is_registration_open(now)

    def is_ca_deadline_passed(self, now=None):
        """Check if CA submission deadline has passed."""
        if now is None:
            from django.utils import timezone

            now = timezone.now()
        if self.ca_submission_deadline_at:
            return now > self.ca_submission_deadline_at
        return False

    def has_admin_override(self, override_type: str) -> bool:
        """Check if an admin override exists for a specific lock type."""
        return bool(self.admin_overrides.get(f"{override_type}_override"))

    def set_admin_override(self, override_type: str, user, reason: str = ""):
        """Record an admin override (audit trail)."""
        from django.utils import timezone

        if not self.admin_overrides:
            self.admin_overrides = {}
        self.admin_overrides[f"{override_type}_override"] = {
            "by": user.id if hasattr(user, "id") else None,
            "by_username": user.username if hasattr(user, "username") else str(user),
            "at": timezone.now().isoformat(),
            "reason": reason or "",
        }
        self.save(update_fields=["admin_overrides"])

    def clear_admin_override(self, override_type: str):
        """Remove an admin override."""
        if self.admin_overrides and f"{override_type}_override" in self.admin_overrides:
            del self.admin_overrides[f"{override_type}_override"]
            self.save(update_fields=["admin_overrides"])

    def can_add_candidates(self, user=None, check_override=True):
        """Check if candidates can be added (respects deadlines + admin override)."""
        if not self.is_registration_open():
            if (
                check_override
                and user
                and self.has_admin_override("registration_locked")
            ):
                return True
            return False
        return True

    def can_edit_candidates(self, user=None, check_override=True):
        """Check if candidates can be edited (respects deadlines + admin override)."""
        if self.is_registration_locked():
            if (
                check_override
                and user
                and self.has_admin_override("registration_locked")
            ):
                return True
            return False
        return True


class CertificationCandidate(models.Model):
    """Candidate registration record for a certification exam session."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        VERIFIED = "VERIFIED", "Verified"
        EXPORTED = "EXPORTED", "Exported"
        ARCHIVED = "ARCHIVED", "Archived"

    session = models.ForeignKey(
        CertificationExamSession, on_delete=models.CASCADE, related_name="candidates"
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.PROTECT,
        related_name="certification_candidates",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    # Cameroon 2026: internal candidates must include Unique Identifier (matricule).
    unique_identifier = models.CharField(
        max_length=80,
        blank=True,
        help_text="MINESEC/MINEDUB Unique Identifier (matricule) for internal candidates.",
    )
    official_cin = models.CharField(
        max_length=20,
        blank=True,
        help_text="Official CIN generated by the board e-registration software.",
    )
    candidate_number = models.CharField(
        max_length=60, blank=True, help_text="Board candidate number (if assigned)."
    )
    payment_transaction_id = models.CharField(
        max_length=120,
        blank=True,
        help_text="Payment gateway transaction/reference id used for validation (Stripe, MTN MoMo, Paystack, etc.).",
    )
    payment_amount_fcfa = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Amount paid in the tenant's fee-template currency (legacy column name retained for "
            "backwards compatibility — value is not assumed to be in FCFA). Use the linked "
            "CertificationFeeTemplate.currency for display."
        ),
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    ca_uploaded_at = models.DateTimeField(null=True, blank=True)
    # v4.00.13: per-candidate continuous-assessment marks. Shape:
    #   {"total": <number>, "subjects": {"<code>": <number>, ...}}
    # Read by the export_certification_pack command; written by the
    # CAMarksInputView at /school/studio/certification/ca-marks/.
    continuous_assessment = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student__last_name", "student__first_name"]
        unique_together = ("session", "student")

    def __str__(self):
        return f"{self.student} - {self.session}"


class CertificationAuditLog(models.Model):
    """Minimal audit trail for certification workflow actions."""

    session = models.ForeignKey(
        CertificationExamSession, on_delete=models.CASCADE, related_name="audit_logs"
    )
    candidate = models.ForeignKey(
        CertificationCandidate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    action = models.CharField(max_length=120)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class CertificationExamPreset(models.Model):
    """
    Reusable rules/config for a certification exam type.
    Examples: GCE General O-Level, GCE General A-Level, Technical (CAP/Probatoire/Bac) / OBC style.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="certification_exam_presets",
    )

    class Board(models.TextChoices):
        GCE_BOARD = "GCE_BOARD", "GCE Board (Cameroon)"
        OBC = "OBC", "Office du Baccalauréat du Cameroun (OBC)"
        WAEC = "WAEC", "WAEC (West Africa)"
        NECO = "NECO", "NECO (Nigeria)"
        KCSE = "KCSE", "KCSE (Kenya)"
        IGCSE_CIE = "IGCSE_CIE", "Cambridge IGCSE"
        IB = "IB", "International Baccalaureate (IB)"
        AP_CB = "AP_CB", "College Board (AP/SAT)"
        BAC_FR = "BAC_FR", "Baccalauréat (France)"
        ABITUR_DE = "ABITUR_DE", "Abitur (Germany)"
        STATE_BOARD = "STATE_BOARD", "State/Provincial Board"
        OTHER = "OTHER", "Other"

    class Level(models.TextChoices):
        O_LEVEL = "O_LEVEL", "O-Level / IGCSE"
        A_LEVEL = "A_LEVEL", "A-Level / Advanced"
        TECHNICAL = "TECHNICAL", "Technical / Vocational"
        DIPLOMA = "DIPLOMA", "Diploma"
        OTHER = "OTHER", "Other"

    code = models.CharField(
        max_length=40,
        help_text="Short code, e.g. GCE_OLEVEL_2026, IGCSE_2026, WAEC_SSCE, BAC_FR_2026.",
    )
    name = models.CharField(max_length=160)  # magic-number-allow: charfield-max-length
    board = models.CharField(
        max_length=20, choices=Board.choices, default=Board.OTHER
    )
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.OTHER)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # Flexible configuration payloads (kept JSON so different boards/years can evolve).
    rules = models.JSONField(
        default=dict,
        blank=True,
        help_text="Validation rules (e.g., allowed classes, required fields, subject selection rules).",
    )
    ca_export_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="CA export mapping config (e.g., subject columns/weights required by the board software).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["board", "level", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"], name="unique_cert_exam_preset_code"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_board_display()} / {self.get_level_display()})"


class CertificationFeeTemplate(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="certification_fee_templates",
    )
    """
    A fee template for an exam preset (or directly assigned to a session).
    Common patterns in Cameroon:
    - Fixed registration/admin fee
    - Per-subject fees
    - Practical fees for some subjects/specialties
    """

    preset = models.ForeignKey(
        CertificationExamPreset,
        on_delete=models.CASCADE,
        related_name="fee_templates",
        null=True,
        blank=True,
        help_text="Attach to a preset to reuse across sessions. Leave blank for a one-off template.",
    )
    name = models.CharField(max_length=160)  # magic-number-allow: charfield-max-length
    currency = models.CharField(max_length=10, default=_default_currency)
    is_default_for_preset = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class CertificationFeeLine(models.Model):
    class FeeType(models.TextChoices):
        REGISTRATION = "REGISTRATION", "Registration"
        SUBJECT = "SUBJECT", "Subject fee"
        PRACTICAL = "PRACTICAL", "Practical fee"
        OTHER = "OTHER", "Other"

    template = models.ForeignKey(
        CertificationFeeTemplate, on_delete=models.CASCADE, related_name="lines"
    )
    label = models.CharField(max_length=160)  # magic-number-allow: charfield-max-length
    fee_type = models.CharField(
        max_length=20, choices=FeeType.choices, default=FeeType.OTHER
    )
    amount_fcfa = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Fee amount in the parent template's currency (legacy column name kept for "
            "backwards compatibility — the value is NOT assumed to be FCFA)."
        ),
    )

    # If true, this line is multiplied by the candidate's subject count (later: subject selection model).
    applies_per_subject = models.BooleanField(
        default=False,
        help_text="If enabled, multiply by number of subjects selected by the candidate (configured later).",
    )

    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        currency = ""
        try:
            currency = getattr(self.template, "currency", "") or ""
        except (AttributeError, ValueError):
            currency = ""
        return f"{self.label} ({self.amount_fcfa} {currency})".rstrip()


class CertificationDocumentChecklist(models.Model):
    """Reusable document checklist template for a preset/session."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="certification_document_checklists",
    )
    preset = models.ForeignKey(
        CertificationExamPreset,
        on_delete=models.CASCADE,
        related_name="document_checklists",
        null=True,
        blank=True,
        help_text="Attach to a preset to reuse across sessions. Leave blank for a one-off checklist.",
    )
    name = models.CharField(max_length=160)  # magic-number-allow: charfield-max-length
    is_default_for_preset = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class CertificationDocumentItem(models.Model):
    checklist = models.ForeignKey(
        CertificationDocumentChecklist, on_delete=models.CASCADE, related_name="items"
    )
    code = models.CharField(
        max_length=40, help_text="Short code, e.g. BIRTH_CERT, ID_CARD, PHOTO_4X4."
    )
    label = models.CharField(max_length=160)  # magic-number-allow: charfield-max-length
    required = models.BooleanField(default=True)
    help_text = models.CharField(max_length=240, blank=True)  # magic-number-allow: charfield-max-length
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["checklist", "code"],
                name="unique_cert_doc_item_code_per_checklist",
            ),
        ]

    def __str__(self):
        return self.label


class CertificationCandidateDocumentStatus(models.Model):
    """Per-candidate completion status for each document item."""

    class Status(models.TextChoices):
        MISSING = "MISSING", "Missing"
        RECEIVED = "RECEIVED", "Received"
        VERIFIED = "VERIFIED", "Verified"
        WAIVED = "WAIVED", "Waived"

    candidate = models.ForeignKey(
        CertificationCandidate,
        on_delete=models.CASCADE,
        related_name="document_statuses",
    )
    item = models.ForeignKey(
        CertificationDocumentItem,
        on_delete=models.CASCADE,
        related_name="candidate_statuses",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.MISSING
    )
    received_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "item"], name="unique_cert_candidate_doc_status"
            ),
        ]

    def __str__(self):
        return f"{self.candidate} - {self.item} ({self.get_status_display()})"


class Attendance(models.Model):
    """Per-day student attendance (present, absent, late, excused). Used for roll call and absence alerts to parents."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attendances",
    )

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"

    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PRESENT,
    )
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Client-generated id for an attendance row marked offline on an edge box; lets the
    # operator upsert it by (school, client_offline_id) on sync without pk collisions.
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)

    class Meta:
        ordering = ["-date", "student"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "classroom", "date"],
                name="unique_student_classroom_date_attendance",
            ),
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_attendance_school_offline_id",
            ),
        ]

    def __str__(self):
        return f"{self.student} – {self.date} – {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # Backfill the tenant FK at this single chokepoint. Every school-scoped
        # consumer (attendance CSV export, multi-campus rollup, tenant-overview
        # viz, student-transfer export) filters on school_id, and the offboarding
        # purge deletes by school_id — so a row with school=NULL silently escapes
        # all reporting AND survives a tenant's "permanent" delete as orphan
        # student PII (see apps/wal_stream/writers.py). Several create paths
        # (teacher roll-call, mobile sync, REST record) omit school, so derive it
        # from the student (fallback: classroom). The student/classroom are the
        # roll-call path's already-loaded objects, so this is free there.
        if self.school_id is None:
            self.school_id = getattr(self.student, "school_id", None) or getattr(
                self.classroom, "school_id", None
            )
            if self.school_id is None:
                # Both links are themselves nullable, and under schema-per-tenant
                # they are routinely NULL (the schema already isolates the tenant,
                # so writers omit the redundant FK) — leaving this backfill a
                # silent no-op and the row invisible to every school_id consumer
                # above. The connection's tenant IS the school, so ask it last.
                from apps.schools.rls_context import resolve_connection_school_id

                self.school_id = resolve_connection_school_id()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and "school" not in update_fields:
                kwargs["update_fields"] = list(update_fields) + ["school"]
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        from apps.compliance.attendance_region_packs import (
            attendance_compliance_errors,
            should_enforce_strict_block,
        )

        if should_enforce_strict_block(self):
            errs = attendance_compliance_errors(self)
            if errs:
                raise ValidationError(errs)


class Incident(models.Model):
    """Disciplinary incident (tardiness, behavior, etc.) for students or teachers. Alerts parents when notify_parent is True."""

    class Type(models.TextChoices):
        TARDINESS = "TARDINESS", "Tardiness"
        BEHAVIOR = "BEHAVIOR", "Behavior"
        ABSENCE = "ABSENCE", "Unexcused absence"
        OTHER = "OTHER", "Other"

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    class Status(models.TextChoices):
        REFERRED = "REFERRED", "Referred"
        OPEN = "OPEN", "Open"
        RESOLVED = "RESOLVED", "Resolved"

    class MtssTier(models.TextChoices):
        TIER_1 = "1", "Tier 1 — Universal"
        TIER_2 = "2", "Tier 2 — Targeted"
        TIER_3 = "3", "Tier 3 — Intensive"

    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="incidents",
        null=True,
        blank=True,
    )
    teacher = models.ForeignKey(
        "people.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="incidents",
        null=True,
        blank=True,
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="incidents",
        null=True,
        blank=True,
    )
    incident_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.OTHER
    )
    date = models.DateField()
    description = models.TextField(blank=True)
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.MEDIUM
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    mtss_tier = models.CharField(
        max_length=1,
        choices=MtssTier.choices,
        default=MtssTier.TIER_1,
        blank=True,
    )
    parent_notified_at = models.DateTimeField(null=True, blank=True)
    notify_parent = models.BooleanField(
        default=True,
        help_text="When True, linked guardians are notified (student incidents only).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_incidents",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when a discipline manager marks the incident RESOLVED.",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_incidents",
        help_text="User who resolved the incident (audit trail for the RESOLVED transition).",
    )

    class Meta:
        ordering = ["-date", "-created_at"]

    def save(self, *args, **kwargs):
        """
        Keep tenant ownership aligned with linked student/teacher records.
        Student school takes precedence when both are provided.
        """
        resolved_school_id = self.school_id
        if self.student_id:
            resolved_school_id = (
                getattr(self.student, "school_id", None) or resolved_school_id
            )
        elif self.teacher_id:
            resolved_school_id = (
                getattr(self.teacher, "school_id", None) or resolved_school_id
            )
        self.school_id = resolved_school_id
        super().save(*args, **kwargs)

    def __str__(self):
        who = (self.student or self.teacher) or "—"
        return f"Incident {self.get_incident_type_display()} – {who} – {self.date}"


def _syllabus_upload_to(instance, filename):
    """Tenant-scoped path for CourseSyllabus.uploaded_file (Section 25.3). School from subject_assignment.academic_year."""
    sa = getattr(instance, "subject_assignment", None)
    ay = getattr(sa, "academic_year", None) if sa else None
    school_id = getattr(ay, "school_id", None) if ay else None
    if school_id is None:
        return f"tenant_uploads/academics/syllabi/{filename}"
    return f"tenants/{school_id}/academics/syllabi/{filename}"


class CourseSyllabus(models.Model):
    """
    One syllabus per SubjectAssignment (class + subject + term/year).
    Teacher is determined via TeacherAssignment; approvers use get_effective_approvers(syllabus_approval).
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending approval"
        NEEDS_REVISION = "NEEDS_REVISION", "Needs revision"
        APPROVED = "APPROVED", "Approved"

    subject_assignment = models.OneToOneField(
        SubjectAssignment,
        on_delete=models.CASCADE,
        related_name="course_syllabus",
        unique=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    builder_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured data from the syllabus builder (e.g. CBA sections).",
    )
    uploaded_file = models.FileField(
        upload_to=_syllabus_upload_to,
        null=True,
        blank=True,
        help_text="Optional uploaded PDF/Word instead of or in addition to builder data.",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_syllabi",
    )
    reviewer_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_syllabi",
    )
    portal_item = models.OneToOneField(
        "portal.PortalFeatureItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="course_syllabus",
        help_text="Synced to Document Library / syllabus feature on approval.",
    )
    curriculum_nodes = models.ManyToManyField(
        "CurriculumNode",
        blank=True,
        related_name="course_syllabi",
        help_text="Curriculum standards/topics this syllabus aligns to (Wave 6 standards tagging).",
    )

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Course syllabus"
        verbose_name_plural = "Course syllabi"

    def __str__(self):
        return f"{self.subject_assignment} – {self.get_status_display()}"


class ClassBooklist(models.Model):
    """Booklist per class (academic year; optional term). Configurable list of required books."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="class_booklists",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="class_booklists"
    )
    classroom = models.ForeignKey(
        Classroom, on_delete=models.CASCADE, related_name="booklists"
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="class_booklists",
        help_text="Optional: leave blank for full-year list.",
    )
    items = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {title, author, isbn, notes} or similar.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["classroom__name", "term__position"]
        verbose_name = "Class booklist"
        verbose_name_plural = "Class booklists"
        unique_together = [("academic_year", "classroom", "term")]

    def __str__(self):
        return f"{self.classroom.name} ({self.academic_year.name})"


class CurriculumStandard(models.Model):
    """Curriculum/progression standard (e.g. MINESEC Physics Form 5, Common Core). Country-agnostic."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="curriculum_standards",
    )
    name = models.CharField(max_length=200)
    country_code = models.CharField(
        max_length=10, blank=True, help_text="e.g. CM, US, GB"
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CurriculumNode(models.Model):
    """Hierarchical node (Subject > Unit > Topic) for a standard. Imported via CSV/Excel."""

    class LevelType(models.TextChoices):
        SUBJECT = "subject", "Subject"
        UNIT = "unit", "Unit"
        CHAPTER = "chapter", "Chapter"
        TOPIC = "topic", "Topic"

    standard = models.ForeignKey(
        CurriculumStandard,
        on_delete=models.CASCADE,
        related_name="nodes",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    code = models.CharField(max_length=80, help_text="e.g. PHY-F5-U2-L3")
    title = models.CharField(max_length=300)
    order = models.PositiveSmallIntegerField(default=0)
    level_type = models.CharField(
        max_length=20,
        choices=LevelType.choices,
        default=LevelType.TOPIC,
    )

    class Meta:
        ordering = ["standard", "order", "code"]
        unique_together = [("standard", "code")]

    def __str__(self):
        return f"{self.code} – {self.title}"


# =============================================================================
# Higher Ed: Degree Audit, Graduate Research (Phases 3–4, global platform)
# =============================================================================


class DegreeProgram(models.Model):
    """Degree program (e.g. BSc Computer Science). requirements_json defines required courses/credits/milestones."""

    class TranscriptTrack(models.TextChoices):
        ACADEMIC = "ACADEMIC", "Academic (degree)"
        VOCATIONAL = "VOCATIONAL", "Vocational (certificate)"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="degree_programs",
    )
    name = models.CharField(max_length=200)
    transcript_track = models.CharField(
        max_length=20,
        choices=TranscriptTrack.choices,
        default=TranscriptTrack.ACADEMIC,
        help_text="Used for dual transcript: export by track (academic vs vocational).",
    )
    level = models.CharField(
        max_length=20,
        choices=[
            ("ASC", "Associate"),
            ("BSC", "Bachelor"),
            ("MSC", "Master"),
            ("PHD", "PhD"),
        ],
        default="BSC",
    )
    requirements_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Required credits, course codes, min_gpa, optional milestones_required list.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Degree program"
        verbose_name_plural = "Degree programs"

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"


class StudentDegreeEnrollment(models.Model):
    """Student enrolled in a degree program; used for run_degree_audit."""

    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="degree_enrollments",
    )
    program = models.ForeignKey(
        DegreeProgram,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    start_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        unique_together = [("student", "program")]
        verbose_name = "Student degree enrollment"
        verbose_name_plural = "Student degree enrollments"

    def __str__(self):
        return f"{self.student} — {self.program.name}"


class TransferCredit(models.Model):
    """External credits transferred in (for degree audit)."""

    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="transfer_credits",
    )
    external_institution = models.CharField(max_length=200)
    course_code = models.CharField(max_length=80)
    credits = models.DecimalField(max_digits=6, decimal_places=2)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Transfer credit"
        verbose_name_plural = "Transfer credits"

    def __str__(self):
        return f"{self.course_code} ({self.credits}) from {self.external_institution}"


class TransferCourseEquivalency(models.Model):
    """Reviewable mapping from external transfer course to internal course requirement."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="transfer_course_equivalencies",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="transfer_course_equivalencies",
    )
    program = models.ForeignKey(
        DegreeProgram,
        on_delete=models.CASCADE,
        related_name="transfer_course_equivalencies",
        null=True,
        blank=True,
        help_text="Optional program-specific mapping. Blank means cross-program for the student.",
    )
    transfer_credit = models.ForeignKey(
        TransferCredit,
        on_delete=models.SET_NULL,
        related_name="equivalency_links",
        null=True,
        blank=True,
    )
    external_course_code = models.CharField(max_length=80)
    internal_course_code = models.CharField(max_length=80)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    request_notes = models.TextField(blank=True)
    reviewer_notes = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_transfer_equivalencies",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_transfer_equivalencies",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student",
                    "program",
                    "external_course_code",
                    "internal_course_code",
                ],
                name="academics_transfer_equiv_unique_per_student_program_course_pair",
            ),
        ]
        verbose_name = "Transfer course equivalency"
        verbose_name_plural = "Transfer course equivalencies"

    def __str__(self):
        return f"{self.external_course_code} -> {self.internal_course_code} ({self.status})"


class GraduateMilestone(models.Model):
    """Thesis/dissertation milestone (proposal, candidacy, defense, submission). Gate: graduate_research addon."""

    class Type(models.TextChoices):
        PROPOSAL = "PROPOSAL", "Proposal"
        CANDIDACY = "CANDIDACY", "Candidacy"
        DEFENSE = "DEFENSE", "Defense"
        SUBMISSION = "SUBMISSION", "Submission"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="graduate_milestones",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="graduate_milestones",
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    committee_chair = models.ForeignKey(
        "people.TeacherProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graduate_milestones_chaired",
    )
    status = models.CharField(
        max_length=40, default="PENDING"
    )  # PENDING, COMPLETED, etc.
    target_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    is_signed_off = models.BooleanField(default=False)
    sign_off_timestamp = models.DateTimeField(null=True, blank=True)
    committee_member_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Total committee members on the milestone review panel.",
    )
    external_member_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of external (non-department/non-internal) committee members.",
    )
    embargo_until = models.DateField(
        null=True,
        blank=True,
        help_text="Optional thesis/dissertation embargo end date for submission milestones.",
    )
    embargo_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reason for embargo (e.g. patent filing in progress).",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extensible milestone metadata for institution-specific research requirements.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student", "type"]
        verbose_name = "Graduate milestone"
        verbose_name_plural = "Graduate milestones"

    def clean(self):
        if self.external_member_count > self.committee_member_count:
            raise ValidationError(
                {
                    "external_member_count": "External member count cannot exceed total committee members."
                }
            )
        if self.embargo_until and self.type != self.Type.SUBMISSION:
            raise ValidationError(
                {"embargo_until": "Embargo can only be set for submission milestones."}
            )
        if (
            self.embargo_until
            and self.completion_date
            and self.embargo_until < self.completion_date
        ):
            raise ValidationError(
                {"embargo_until": "Embargo end date cannot be before completion date."}
            )
        if self.embargo_until and not (self.embargo_reason or "").strip():
            raise ValidationError(
                {
                    "embargo_reason": "Provide an embargo reason when embargo_until is set."
                }
            )

    def __str__(self):
        return f"{self.student} — {self.get_type_display()} ({self.status})"


class WorkflowConfig(models.Model):
    """
    World Engine: JSON-driven workflow (tenant schema). workflow_key + steps (JSON);
    generic wizard view loads config and renders steps dynamically. Tenant can reorder steps in admin.
    One row per workflow per tenant (schema = tenant).
    """

    workflow_key = models.CharField(
        max_length=120,
        unique=True,
        help_text="Identifier for this workflow (e.g. student_onboarding, teacher_setup).",
    )
    steps = models.JSONField(
        default=list,
        help_text='Ordered list of steps: [{"id": "step1", "title": "...", "template": "...", "form": "..."}].',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workflow_key"]
        verbose_name = "Workflow configuration"
        verbose_name_plural = "Workflow configurations"

    def __str__(self):
        return self.workflow_key


from .models_tenant_runtime import (  # noqa: E402,F401
    HolidayCalendar,
    ReportCardStyleAssignment,
    RolloverProposal,
    RolloverProposalItem,
)
# Education-system phase 2: minimal LMS spine (Assignment + Submission).
from .models_lms import LMSAssignment, LMSSubmission  # noqa: E402,F401
from .instruction_day_ledger import InstructionDay  # noqa: E402,F401
from .academic_structure import AcademicStructureNode  # noqa: E402,F401
from .models_discipline import BehaviorPointLedger, RestorativeAction  # noqa: E402,F401
from .scheduling import InstructionShift  # noqa: E402,F401
