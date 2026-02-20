from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError


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

    def __init__(self, *args, **kwargs):
        # Backwards-compatibility: accept `starts_on`/`ends_on` kwargs used by older code/tests
        if 'starts_on' in kwargs:
            kwargs['start_date'] = kwargs.pop('starts_on')
        if 'ends_on' in kwargs:
            kwargs['end_date'] = kwargs.pop('ends_on')
        super().__init__(*args, **kwargs)

    @property
    def starts_on(self):
        return self.start_date

    @property
    def ends_on(self):
        return self.end_date

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


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
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    # Code identifier (free text, e.g., "FIRST", "SEM1", "Q1"). No choices to enable flexibility.
    name = models.CharField(max_length=20)
    # Optional custom label for flexible naming (e.g., "Semester 1").
    custom_label = models.CharField(max_length=30, blank=True)
    # Position within the academic year (1..4) to support 2–4 terms configuration.
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    def __init__(self, *args, **kwargs):
        # Backwards-compatibility: accept keyword 'order' used by older code/tests
        if 'order' in kwargs:
            kwargs['position'] = kwargs.pop('order')
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
                check=(Q(position__isnull=True) | (Q(position__gte=1) & Q(position__lte=4))),
                name="term_position_range_1_4_or_null",
            ),
        ]

    def clean(self):
        super().clean()
        if self.position is not None and not (1 <= int(self.position) <= 4):
            raise ValidationError({"position": "Position must be between 1 and 4."})

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
    code = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ["name"]

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
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="specialties")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ["name"]

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
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="classrooms")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="classrooms")
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

    class Meta:
        ordering = ["name"]

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
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"],
                name="academics_subject_school_name_uniq",
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
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="subject_assignments")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="subject_assignments")
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT, related_name="subject_assignments")
    specialty = models.ForeignKey(Specialty, on_delete=models.PROTECT, related_name="subject_assignments")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="subject_assignments")
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    grading_deadline_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional deadline for completing grades for this assignment (term/class/subject).",
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
        GCE_BOARD = "GCE_BOARD", "GCE Board"
        OBC = "OBC", "Office du Baccalauréat du Cameroun (OBC)"
        OTHER = "OTHER", "Other"

    class Level(models.TextChoices):
        O_LEVEL = "O_LEVEL", "GCE O-Level"
        A_LEVEL = "A_LEVEL", "GCE A-Level"
        TECHNICAL = "TECHNICAL", "Technical (CAP/Probatoire/Bac)"
        OTHER = "OTHER", "Other"

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="certification_sessions")
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
    board = models.CharField(max_length=20, choices=Board.choices, default=Board.GCE_BOARD)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.OTHER)
    name = models.CharField(max_length=120, help_text="e.g., 'GCE Registration 2026 - O Level'")
    exam_centre_name = models.CharField(max_length=200, blank=True)
    exam_centre_number = models.CharField(max_length=40, blank=True, help_text="Official centre number used by the board portal.")
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
            if check_override and user and self.has_admin_override("registration_locked"):
                return True
            return False
        return True

    def can_edit_candidates(self, user=None, check_override=True):
        """Check if candidates can be edited (respects deadlines + admin override)."""
        if self.is_registration_locked():
            if check_override and user and self.has_admin_override("registration_locked"):
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

    session = models.ForeignKey(CertificationExamSession, on_delete=models.CASCADE, related_name="candidates")
    student = models.ForeignKey("people.StudentProfile", on_delete=models.PROTECT, related_name="certification_candidates")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # Cameroon 2026: internal candidates must include Unique Identifier (matricule).
    unique_identifier = models.CharField(max_length=80, blank=True, help_text="MINESEC/MINEDUB Unique Identifier (matricule) for internal candidates.")
    official_cin = models.CharField(max_length=20, blank=True, help_text="Official CIN generated by the board e-registration software.")
    candidate_number = models.CharField(max_length=60, blank=True, help_text="Board candidate number (if assigned).")
    payment_transaction_id = models.CharField(max_length=120, blank=True, help_text="MTN Mobile Money transaction/payment ID used for validation.")
    payment_amount_fcfa = models.PositiveIntegerField(default=0, help_text="Amount paid (FCFA).")
    validated_at = models.DateTimeField(null=True, blank=True)
    ca_uploaded_at = models.DateTimeField(null=True, blank=True)
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

    session = models.ForeignKey(CertificationExamSession, on_delete=models.CASCADE, related_name="audit_logs")
    candidate = models.ForeignKey(CertificationCandidate, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    actor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
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
        GCE_BOARD = "GCE_BOARD", "GCE Board"
        OBC = "OBC", "Office du Baccalauréat du Cameroun (OBC)"
        OTHER = "OTHER", "Other"

    class Level(models.TextChoices):
        O_LEVEL = "O_LEVEL", "GCE O-Level"
        A_LEVEL = "A_LEVEL", "GCE A-Level"
        TECHNICAL = "TECHNICAL", "Technical (CAP/Probatoire/Bac)"
        OTHER = "OTHER", "Other"

    code = models.CharField(
        max_length=40,
        help_text="Short code, e.g. GCE_OLEVEL_2026, GCE_ALEVEL, OBC_BAC.",
    )
    name = models.CharField(max_length=160)
    board = models.CharField(max_length=20, choices=Board.choices, default=Board.GCE_BOARD)
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
            models.UniqueConstraint(fields=["code"], name="unique_cert_exam_preset_code"),
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
    name = models.CharField(max_length=160)
    currency = models.CharField(max_length=10, default="XAF")
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

    template = models.ForeignKey(CertificationFeeTemplate, on_delete=models.CASCADE, related_name="lines")
    label = models.CharField(max_length=160)
    fee_type = models.CharField(max_length=20, choices=FeeType.choices, default=FeeType.OTHER)
    amount_fcfa = models.PositiveIntegerField(default=0)

    # If true, this line is multiplied by the candidate's subject count (later: subject selection model).
    applies_per_subject = models.BooleanField(
        default=False,
        help_text="If enabled, multiply by number of subjects selected by the candidate (configured later).",
    )

    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.label} ({self.amount_fcfa} FCFA)"


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
    name = models.CharField(max_length=160)
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
    checklist = models.ForeignKey(CertificationDocumentChecklist, on_delete=models.CASCADE, related_name="items")
    code = models.CharField(max_length=40, help_text="Short code, e.g. BIRTH_CERT, ID_CARD, PHOTO_4X4.")
    label = models.CharField(max_length=160)
    required = models.BooleanField(default=True)
    help_text = models.CharField(max_length=240, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["checklist", "code"], name="unique_cert_doc_item_code_per_checklist"),
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

    candidate = models.ForeignKey(CertificationCandidate, on_delete=models.CASCADE, related_name="document_statuses")
    item = models.ForeignKey(CertificationDocumentItem, on_delete=models.CASCADE, related_name="candidate_statuses")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.MISSING)
    received_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["candidate", "item"], name="unique_cert_candidate_doc_status"),
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

    class Meta:
        ordering = ["-date", "student"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "classroom", "date"],
                name="unique_student_classroom_date_attendance",
            ),
        ]

    def __str__(self):
        return f"{self.student} – {self.date} – {self.get_status_display()}"


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
    incident_type = models.CharField(max_length=20, choices=Type.choices, default=Type.OTHER)
    date = models.DateField()
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
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

    class Meta:
        ordering = ["-date", "-created_at"]

    def save(self, *args, **kwargs):
        """
        Keep tenant ownership aligned with linked student/teacher records.
        Student school takes precedence when both are provided.
        """
        resolved_school_id = self.school_id
        if self.student_id:
            resolved_school_id = getattr(self.student, "school_id", None) or resolved_school_id
        elif self.teacher_id:
            resolved_school_id = getattr(self.teacher, "school_id", None) or resolved_school_id
        self.school_id = resolved_school_id
        super().save(*args, **kwargs)

    def __str__(self):
        who = (self.student or self.teacher) or "—"
        return f"Incident {self.get_incident_type_display()} – {who} – {self.date}"


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
        upload_to="syllabi/%Y/%m/",
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
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="class_booklists")
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="booklists")
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
    country_code = models.CharField(max_length=10, blank=True, help_text="e.g. CM, US, GB")
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
