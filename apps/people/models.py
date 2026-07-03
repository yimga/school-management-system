from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

import re
import uuid

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Specialty, Department


def _people_tenant_upload_to(subpath):
    """Tenant-prefixed upload_to for models with school_id (Section 25.3). Inline to avoid circular import with siteconfig."""

    def upload_to(instance, filename):
        school_id = getattr(instance, "school_id", None) or (
            getattr(getattr(instance, "school", None), "pk", None)
            if getattr(instance, "school", None)
            else None
        )
        if school_id is None:
            return f"tenant_uploads/people/{subpath}/{filename}"
        return f"tenants/{school_id}/people/{subpath}/{filename}"

    return upload_to


def tenant_upload_to_teacher_profile_photo(instance, filename):
    """Serializable upload_to for TeacherProfile.profile_photo (Section 25.3)."""
    return _people_tenant_upload_to("profiles/teachers")(instance, filename)


def tenant_upload_to_student_profile_photo(instance, filename):
    """Serializable upload_to for StudentProfile.profile_photo (Section 25.3)."""
    return _people_tenant_upload_to("profiles/students")(instance, filename)


def tenant_upload_to_special_education_plan(instance, filename):
    """Serializable upload_to for SpecialEducationPlan.plan_document."""
    return _people_tenant_upload_to("special_education_plans")(instance, filename)


def _passport_doc_upload_to(instance, filename):
    """Tenant-scoped path for PassportDocument; uses verified_by_school_id when set (Section 25.3)."""
    school_id = getattr(instance, "verified_by_school_id", None)
    now = timezone.now()
    subpath = f"people/passport_docs/{now:%Y/%m}"
    if school_id is None:
        return f"tenant_uploads/{subpath}/{filename}"
    return f"tenants/{school_id}/{subpath}/{filename}"


# -----------------------------------------------------------------------------
# Information Tagging (zero hardcoding): school-defined categories for students
# -----------------------------------------------------------------------------


class InformationTag(models.Model):
    """
    School-defined tags (e.g. "Scholarship Student", "Athletic Team A", "Allergy: Nut").
    No hardcoded columns on Student — all nuance is data-driven for the AI Nuance Engine.
    Security: tags are scoped by school (tenant). is_private = only Medical/Admin can see.
    is_critical = when added to a student, can trigger dispute workflow / Principal notification.
    """

    class Category(models.TextChoices):
        MEDICAL = "MED", _("Medical")
        FINANCIAL = "FIN", _("Financial")
        ACADEMIC = "ACA", _("Academic")
        GENERAL = "GEN", _("General")

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="information_tags",
    )
    name = models.CharField(
        max_length=50, help_text=_("e.g. Asthma, Early Bird, Scholarship")
    )
    category = models.CharField(
        max_length=3, choices=Category.choices, default=Category.GENERAL
    )
    color_hex = models.CharField(max_length=7, default="#3498db")
    description = models.TextField(
        blank=True, help_text=_("Metadata for the AI Nuance Engine")
    )
    is_private = models.BooleanField(
        default=False,
        help_text=_(
            "Only users with Medical or Admin permissions can see this tag on students."
        ),
    )
    is_critical = models.BooleanField(
        default=False,
        help_text=_(
            "When this tag is added to a student, a notification or support workflow can be triggered."
        ),
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "sort_order", "name"]
        unique_together = [("school", "name")]
        verbose_name = _("Information tag")
        verbose_name_plural = _("Information tags")

    def __str__(self):
        return f"{self.get_category_display()}: {self.name}"


class TeacherProfile(models.Model):
    # Phase 4: Enable audit logging for this model (teacher record changes)
    audit_enabled = True

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="teacher_profiles",
    )

    class DashboardView(models.TextChoices):
        OVERVIEW = "OVERVIEW", "Overview"
        FINANCE = "FINANCE", "Finances"
        ACADEMICS = "ACADEMICS", "Academics"
        ATTENDANCE = "ATTENDANCE", "Attendance"

    staff_id = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    profile_photo = models.ImageField(
        upload_to=tenant_upload_to_teacher_profile_photo,
        blank=True,
        null=True,
    )
    position_title = models.CharField(max_length=120, blank=True)
    reports_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_reports",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teachers",
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="teacher_profile"
    )
    is_active = models.BooleanField(default=True)
    pay_grade = models.CharField(
        max_length=50,
        blank=True,
        help_text="Legacy pay grade field (text). Consider using pay_scale instead.",
    )
    pay_scale = models.ForeignKey(
        "payroll.PayScale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_profiles",
        help_text="Structured pay scale/grade assigned to this teacher",
    )
    salary_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    salary_cap = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    next_pay_date = models.DateField(null=True, blank=True)
    paystub_notes = models.TextField(blank=True)
    custom_attributes = models.JSONField(
        default=dict,
        blank=True,
        help_text="School-defined custom fields (key/value). Use in reports and exports.",
    )
    # First-class offline idempotency anchor (DB-enforced via the partial unique
    # constraint in Meta) — a JSON sub-key cannot be uniquely constrained, so the
    # offline create dedupes on this instead.
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)

    class PaymentMethod(models.TextChoices):
        MTN_MOMO = "MTN_MOMO", "MTN Mobile Money"
        ORANGE_MOMO = "ORANGE_MOMO", "Orange Money"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
        CHECK = "CHECK", "Check"
        CASH = "CASH", "Cash"

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK_TRANSFER,
    )
    default_dashboard_view = models.CharField(
        max_length=20,
        choices=DashboardView.choices,
        default=DashboardView.OVERVIEW,
    )
    allow_finance_panel = models.BooleanField(default=True)
    allow_paystub_access = models.BooleanField(default=True)
    allow_leave_approvals = models.BooleanField(default=False)
    mark_reminder_opt_in = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def suggested_dashboard_view(self) -> str:
        """
        Suggest a dashboard based on position/role keywords.
        """
        title = (self.position_title or "").lower()
        if any(k in title for k in ["finance", "hr", "bursar"]):
            return self.DashboardView.FINANCE
        if any(k in title for k in ["discipline", "attendance", "pastoral"]):
            return self.DashboardView.ATTENDANCE
        if any(
            k in title
            for k in ["principal", "director", "dean", "head", "vice principal"]
        ):
            return self.DashboardView.OVERVIEW
        return self.default_dashboard_view or self.DashboardView.OVERVIEW

    def save(self, *args, **kwargs):
        # Only auto-adjust if a specific default hasn't been chosen yet.
        if (
            self.position_title
            and self.default_dashboard_view == self.DashboardView.OVERVIEW
        ):
            suggested = self.suggested_dashboard_view()
            if suggested != self.default_dashboard_view:
                self.default_dashboard_view = suggested
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_teacherprofile_school_offline_id",
            ),
        ]

    def clean(self):
        # Ensure the linked user is a teacher-aligned role
        allowed_roles = {
            User.Role.TEACHER,
            getattr(User.Role, "DEPT_LEAD", User.Role.TEACHER),
            getattr(User.Role, "LEADERSHIP", User.Role.TEACHER),
        }
        if self.user and self.user.role not in allowed_roles:
            raise ValidationError(
                "TeacherProfile user must have a teacher or department-lead role"
            )

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}"


class TeacherPayRecord(models.Model):
    class RecordType(models.TextChoices):
        PAY = "PAY", "Pay"
        RAISE = "RAISE", "Raise/Stipend"
        BONUS = "BONUS", "Bonus"

    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.CASCADE, related_name="pay_records"
    )
    record_type = models.CharField(
        max_length=12, choices=RecordType.choices, default=RecordType.PAY
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_pay_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-created_at"]

    def __str__(self):
        return f"{self.get_record_type_display()} {self.amount} for {self.teacher}"


class TeacherLeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.CASCADE, related_name="leave_requests"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    approver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_leave_requests",
    )
    decision_notes = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Leave {self.teacher} {self.start_date} -> {self.end_date} ({self.status})"
        )


class TeacherAttendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"
        LATE = "LATE", "Late"
        ON_LEAVE = "ON_LEAVE", "On leave"

    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.CASCADE, related_name="attendance_logs"
    )
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PRESENT
    )
    remarks = models.CharField(max_length=255, blank=True)
    # Nullable on purpose: existing rows backfill to NULL (no one-off default
    # prompt). The WAL drain treats a NULL updated_at as "no known online time"
    # → the offline write wins, which is the safe last-writer-wins default. Every
    # save() from here on stamps it (auto_now), so conflict detection engages for
    # all rows touched after this migration.
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        unique_together = ("teacher", "date")
        ordering = ["-date", "-check_in"]

    def __str__(self):
        return f"{self.teacher} {self.date} ({self.status})"


class StudentProfile(models.Model):
    # Phase 4: Enable audit logging for this model (student record changes, grades tied to this)
    audit_enabled = True

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="student_profiles",
    )
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
    )

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    # Unique PER SCHOOL (Meta constraints), not globally — schools issue their
    # own identifiers, and an inter-school transfer deliberately lands the same
    # number at the target while the source row retires as TRANSFERRED.
    student_code = models.CharField(max_length=50, blank=True, db_index=True)
    admission_number = models.CharField(
        max_length=64, blank=True, null=True, db_index=True
    )
    search_index = models.TextField(
        blank=True,
        default="",
        help_text="Precomputed lowercase search text for backend list FTS.",
    )
    profile_photo = models.ImageField(
        upload_to=tenant_upload_to_student_profile_photo,
        blank=True,
        null=True,
    )

    class Gender(models.TextChoices):
        MALE = "MALE", "Male"
        FEMALE = "FEMALE", "Female"
        NON_BINARY = "NON_BINARY", "Non-binary"
        OTHER = "OTHER", "Other"
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefer not to say"

    class Status(models.TextChoices):
        NEW = "NEW", "New"
        RETURNING = "RETURNING", "Returning"
        PROBATION = "PROBATION", "Probation"
        ALUMNI = "ALUMNI", "Alumni"
        TRANSFERRED = "TRANSFERRED", "Transferred"

    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, blank=True, choices=Status.choices)
    # Duplicate-merge tombstone (Wave C): the retired duplicate points at the
    # surviving row. Soft-retire only — merged rows are never hard-deleted.
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_duplicates",
    )
    # Free-text code to store the joined term (now dynamic). Use portal form for choices.
    joined_term = models.CharField(max_length=20, blank=True)
    joined_date = models.DateField(null=True, blank=True)
    section = models.CharField(max_length=80, blank=True)
    parent_phone = models.CharField(max_length=50, blank=True)
    referral_code = models.CharField(max_length=80, blank=True)

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="students",
        null=True,
        blank=True,
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.PROTECT,
        related_name="students",
        null=True,
        blank=True,
    )
    specialty = models.ForeignKey(
        Specialty,
        on_delete=models.PROTECT,
        related_name="students",
        null=True,
        blank=True,
    )

    # Exam system fields (configurable for different countries    )
    custom_attributes = models.JSONField(
        default=dict,
        blank=True,
        help_text="School-defined custom fields (key/value). Use in reports and exports.",
    )
    # First-class offline idempotency anchor (DB-enforced via Meta constraint).
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)
    exam_candidate_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="National exam candidate number (e.g., GCE, WAEC, etc.)",
    )
    exam_center_code = models.CharField(
        max_length=20, blank=True, help_text="Exam center code"
    )
    exam_system = models.CharField(
        max_length=50, blank=True, help_text="Exam system (e.g., GCE, WAEC, IB, etc.)"
    )

    is_active = models.BooleanField(default=True)
    uses_transport = models.BooleanField(
        default=False,
        help_text="Student uses school bus/transport; transport fee will be added to fee invoices when the plan includes a Transport fee item.",
    )

    # Audit logging fields for data integrity
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Soft delete timestamp - preserves grade history when student leaves",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students_created",
        help_text="User who created this student record",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students_updated",
        help_text="User who last updated this student record",
    )
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    # Zero-hardcoding: school-defined tags (Scholarship, Allergy, Early Bird, etc.)
    tags = models.ManyToManyField(
        InformationTag,
        blank=True,
        related_name="students",
        help_text=_(
            "School-defined information tags for nuance, discounts, and workflows."
        ),
    )
    # Lifetime identity: optional link to StudentPassport for cross-school transcript portability
    passport = models.ForeignKey(
        "StudentPassport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="school_profiles",
        help_text=_(
            "Lifetime student passport (verified transcripts, invite new school to view)."
        ),
    )

    # Dual transcript (Plan XI): program/track for academic vs vocational vs dual report templates
    class TranscriptTrack(models.TextChoices):
        ACADEMIC = "ACADEMIC", _("Academic")
        VOCATIONAL = "VOCATIONAL", _("Vocational")
        DUAL = "DUAL", _("Dual (academic + vocational)")

    transcript_track = models.CharField(
        max_length=20,
        choices=TranscriptTrack.choices,
        default=TranscriptTrack.ACADEMIC,
        blank=True,
        help_text=_(
            "Used by report templates for dual transcript (academic + vocational sections)."
        ),
    )

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_studentprofile_school_offline_id",
            ),
            models.UniqueConstraint(
                fields=["school", "student_code"],
                condition=~models.Q(student_code=""),
                name="uniq_studentprofile_school_student_code",
            ),
            models.UniqueConstraint(
                fields=["school", "admission_number"],
                condition=~models.Q(admission_number=""),
                name="uniq_studentprofile_school_admission_no",
            ),
        ]

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.student_code})"

    def get_full_name(self) -> str:
        """
        Canonical full name for admin displays and templates.
        Falls back to linked user or student_code when needed.
        """
        name = " ".join(p for p in [self.first_name, self.last_name] if p).strip()
        if name:
            return name
        if self.user:
            return self.user.get_full_name() or self.user.username
        return self.student_code or "Student"

    def delete(self, using=None, keep_parents=False, hard_delete: bool = False):
        """
        Soft delete by default to preserve academic/legal audit history.
        Pass hard_delete=True only for explicit data-purge workflows.
        """
        if hard_delete:
            return super().delete(using=using, keep_parents=keep_parents)
        if self.deleted_at:
            return (0, {})
        self.deleted_at = timezone.now()
        fields = ["deleted_at", "updated_at"]
        if self.is_active:
            self.is_active = False
            fields.append("is_active")
        self.save(update_fields=fields)
        return (1, {self._meta.label: 1})

    @property
    def parent_completeness(self) -> int:
        """
        Rough completeness meter based on guardian links and contact fields.
        """
        guardians = list(self.guardian_links.all())
        if not guardians:
            return 0
        score = 0
        for g in guardians:
            if g.phone:
                score += 1
            if g.address:
                score += 1
            if g.preferred_contact:
                score += 1
        # max 3 points per guardian; normalize to 100
        max_points = len(guardians) * 3
        return int(round((score / max_points) * 100)) if max_points else 0

    @staticmethod
    def _class_segment(classroom: Classroom) -> str:
        """
        Attempt to derive a class/form segment from the classroom code.
        Falls back to the last character or '00' if none found.
        """
        if classroom and classroom.code:
            match = re.search(r"(\d+)$", classroom.code)
            if match:
                return match.group(1)
            return classroom.code[:2].upper()
        return "00"

    @classmethod
    def _get_admissions_policy(cls, school=None, policy=None):
        """Single read path for admissions config: policy first (request.tenant_runtime.policy or policy_registry), else platform identifier defaults."""
        if policy is not None and isinstance(policy, dict):
            adm = policy.get("admissions") or {}
            if adm:
                return adm
        if school is not None:
            from apps.policies.policy_registry import get_effective_policy

            policy = get_effective_policy(school)
            adm = policy.get("admissions") or {}
            if adm:
                return adm
        from apps.siteconfig.identifier_policy_service import default_school_code_for

        # Platform default when policy has no admissions; tenant reads via policy/runtime only.
        school_code = default_school_code_for(school) if school else "SCH"
        return {
            "school_code": school_code,
            "admission_number_template": "",
            "admission_number_strategy": "FULL",
            "admission_number_mode": "AUTO_OR_MANUAL",
            "admission_number_pattern": "",
        }

    @classmethod
    def generate_admission_number(
        cls,
        academic_year: AcademicYear,
        specialty: Specialty,
        classroom: Classroom,
        school=None,
    ) -> str:
        """
        Configurable generation: admissions shape from get_effective_policy(school) when present, else defaults from _get_admissions_policy.
        Placeholders: year_2digit, school_code, seq_4digit, spec_code, class_segment.
        """
        school = school or getattr(academic_year, "school", None)
        admissions = cls._get_admissions_policy(school)
        from apps.siteconfig.identifier_policy_service import default_school_code_for

        school_code = (
            admissions.get("school_code") or default_school_code_for(school)
        ).upper()

        year_str = (academic_year.name or "")[:4]
        yy = year_str[-2:] if year_str and year_str[:4].isdigit() else "00"

        seq = cls.objects.filter(academic_year=academic_year).count() + 1
        seq_str = f"{seq:04d}"

        spec_segment = (specialty.code or "XX").upper()[:6] if specialty else "XX"
        class_segment = cls._class_segment(classroom)
        spec_segment = re.sub(r"[^A-Z0-9]", "", spec_segment)
        class_segment = re.sub(r"[^A-Z0-9]", "", class_segment)

        template = (admissions.get("admission_number_template") or "").strip()
        if template:
            return template.format(
                year_2digit=yy,
                school_code=school_code,
                seq_4digit=seq_str,
                spec_code=spec_segment,
                class_segment=class_segment,
            )

        strategy = admissions.get("admission_number_strategy") or "FULL"
        if strategy == "YEAR_SEQ":
            return f"{yy}{school_code}{seq_str}"
        if strategy == "SEQ_ONLY":
            return seq_str

        return f"{yy}{school_code}{seq_str}{spec_segment}{class_segment}"

    def save(self, *args, **kwargs):
        # Auto-generate admission number when not provided, from policy (admission_number_mode).
        if (
            getattr(self, "academic_year_id", None)
            and getattr(self, "specialty_id", None)
            and getattr(self, "classroom_id", None)
        ):
            school = (
                getattr(self.academic_year, "school", None)
                if getattr(self, "academic_year", None)
                else None
            )
            admissions = self._get_admissions_policy(school)
            mode = admissions.get("admission_number_mode") or "AUTO_OR_MANUAL"
            auto_modes = ("AUTO", "AUTO_OR_MANUAL")
            auto_allowed = mode in auto_modes

            if auto_allowed and not self.admission_number:
                from apps.academics.models import AcademicYear, Classroom, Specialty

                # tenant-isolation-allow: model-meta-or-manager-default-scopes-tenant-fk
                year = AcademicYear.objects.get(id=self.academic_year_id)
                specialty = Specialty.objects.get(id=self.specialty_id)
                # tenant-isolation-allow: model-meta-or-manager-default-scopes-tenant-fk
                classroom = Classroom.objects.get(id=self.classroom_id)
                self.admission_number = self.generate_admission_number(
                    year, specialty, classroom, school=school
                )
        if not self.student_code:
            self.student_code = (
                self.admission_number or f"TEMP-{uuid.uuid4().hex[:8].upper()}"
            )
        if not self.referral_code:
            self.referral_code = f"REF-{uuid.uuid4().hex[:6].upper()}"
        from apps.people.student_search_index import build_student_search_index

        self.search_index = build_student_search_index(self)
        super().save(*args, **kwargs)

    def clean(self):
        """Validate admission number format from policy (admission_number_pattern)."""
        if self.admission_number:
            school = (
                getattr(self.academic_year, "school", None)
                if getattr(self, "academic_year", None)
                else None
            )
            admissions = self._get_admissions_policy(school)
            pattern = (admissions.get("admission_number_pattern") or "").strip()
            if not pattern:
                new_style = r"^\d{2}[A-Z0-9]{2,10}\d{4}[A-Z0-9]{2,6}[A-Z0-9]{1,4}$"
                legacy = r"^\d{2}-[A-Z0-9]{2,10}-\d{4}-[A-Z0-9]{2,6}-[A-Z0-9]{1,4}$"
                pattern = rf"({new_style}|{legacy})"
            if not re.match(pattern, self.admission_number):
                raise ValidationError(
                    {
                        "admission_number": _(
                            "Admission number must match the required format (YY + SCHOOL + #### + SPEC + CLASS or legacy dashed)."
                        )
                    }
                )
        super().clean()


# Backwards-compatibility alias
# Older code/tests import `Student` from apps.people.models — keep this alias to avoid ImportError
Student = StudentProfile


class StudentGuardian(models.Model):
    """
    Links a Parent user to one or more students.
    """

    class Relationship(models.TextChoices):
        MOTHER = "MOTHER", "Mother"
        FATHER = "FATHER", "Father"
        GUARDIAN = "GUARDIAN", "Guardian"
        OTHER = "OTHER", "Other"

    class PreferredContact(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        PHONE = "PHONE", "Phone Call"

    guardian_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="guardian_links"
    )
    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="guardian_links"
    )

    relationship = models.CharField(
        max_length=20, choices=Relationship.choices, default=Relationship.GUARDIAN
    )
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    whatsapp_number = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=255, blank=True)
    preferred_contact = models.CharField(
        max_length=20,
        choices=PreferredContact.choices,
        default=PreferredContact.EMAIL,
    )
    receives_email = models.BooleanField(default=True)
    receives_sms = models.BooleanField(default=False)
    receives_whatsapp = models.BooleanField(default=False)
    can_view_results = models.BooleanField(default=True)
    can_view_finance = models.BooleanField(default=False)

    class Meta:
        unique_together = ("guardian_user", "student")

    def clean(self):
        # Allow PARENT or TEACHER (dual-role: teacher who is also a parent uses same account)
        if self.guardian_user and self.guardian_user.role not in (
            User.Role.PARENT,
            User.Role.TEACHER,
        ):
            raise ValidationError(
                "StudentGuardian guardian_user must have role PARENT or TEACHER"
            )

    def __str__(self):
        return f"{self.guardian_user.username} -> {self.student}"


# ========== NOTIFICATION PREFERENCES ==========


# NotificationPreference (guardian per-category digest prefs) was retired
# 2026-06-14 (migration 0058): 0 callers, 0 real tests, reverse accessor
# unused. Coarse channel toggles live on StudentGuardian.receives_{email,sms,
# whatsapp}; user-level channels + weekly digest live in
# siteconfig.models_tooling.UserPreference (routed accounts:notification_
# preferences). Its unique per-category cadence was never wired to any send
# path or UI. See docs/CSS_RETIREMENT_DOCKET.md.


class StudentResourceReturn(models.Model):
    """
    Resource return checklist: items (e.g. textbook, laptop) issued to a student per academic year.
    Mark returned_at when the item is returned; optional block on promotion if not returned.
    """

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="resource_returns",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="resource_returns",
    )
    item_label = models.CharField(
        max_length=120,
        help_text="e.g. Textbook, Laptop, Tablet, Lab coat",
    )
    returned_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["academic_year", "student", "item_label"]
        unique_together = ("student", "academic_year", "item_label")
        verbose_name = "Student resource return"
        verbose_name_plural = "Student resource returns"

    def __str__(self):
        status = "Returned" if self.returned_at else "Outstanding"
        return (
            f"{self.student} – {self.item_label} ({self.academic_year.name}) – {status}"
        )


class BadgeType(models.Model):
    """Configurable badge type (e.g. Syllabus Master, Honor Roll, Acting Principal)."""

    class Audience(models.TextChoices):
        STAFF = "STAFF", "Staff"
        STUDENT = "STUDENT", "Student"

    code = models.CharField(max_length=60, unique=True)
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=60,
        blank=True,
        help_text="Icon name/code (e.g. Bootstrap icon class).",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    audience = models.CharField(
        max_length=20, choices=Audience.choices, default=Audience.STAFF
    )
    criteria_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional rule config (e.g. threshold, trigger).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["audience", "sort_order", "code"]
        verbose_name = "Badge type"
        verbose_name_plural = "Badge types"

    def __str__(self):
        return f"{self.label} ({self.get_audience_display()})"


class Badge(models.Model):
    """Awarded badge (staff or student). Trigger-based; optional QR for verification."""

    badge_type = models.ForeignKey(
        BadgeType, on_delete=models.CASCADE, related_name="badges"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="badges",
        help_text="Staff member (for staff badges).",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="badges",
        help_text="Student (for student badges).",
    )
    criteria_met = models.JSONField(default=dict, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    expiry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When badge is automatically revoked (e.g. delegation end).",
    )
    is_physical_printed = models.BooleanField(default=False)
    qr_data = models.CharField(
        max_length=255,
        blank=True,
        help_text="Signed token or payload for QR verification.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]
        verbose_name = "Badge"
        verbose_name_plural = "Badges"

    def __str__(self):
        if self.user_id:
            return f"{self.badge_type.label} – {self.user}"
        return f"{self.badge_type.label} – {self.student}"

    def clean(self):
        super().clean()
        if not self.user_id and not self.student_id:
            raise ValidationError("Set either user (staff) or student.")
        if self.user_id and self.student_id:
            raise ValidationError("Set either user or student, not both.")


class BadgeScanEvent(models.Model):
    """Phase 5: Optional log of badge/ID scan events for attendance and activity tracking."""

    KIND_BADGE = "badge"
    KIND_STAFF = "staff"
    KIND_STUDENT = "student"

    badge = models.ForeignKey(
        Badge,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_events",
        help_text="Set when token was badge:<pk>.",
    )
    token_kind = models.CharField(
        max_length=20,
        choices=(
            (KIND_BADGE, "Badge"),
            (KIND_STAFF, "Staff ID"),
            (KIND_STUDENT, "Student ID"),
        ),
        default=KIND_BADGE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="badge_scan_events_as_subject",
        help_text="Staff member verified (for staff ID).",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="badge_scan_events",
        help_text="Student verified (for student ID).",
    )
    verified_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(
        default=True, help_text="Whether verification succeeded."
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, unpack_ipv4=True)
    user_agent = models.CharField(max_length=255, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-verified_at"]
        verbose_name = "Badge scan event"
        verbose_name_plural = "Badge scan events"

    def __str__(self):
        subject = self.user or self.student or f"Badge#{self.badge_id}"
        return f"Scan {self.verified_at.isoformat()} – {subject} ({self.token_kind})"


# =============================================================================
# Admissions CRM (Phase 5) & Student Success / Retention (Phase 6), global platform
# =============================================================================


class Applicant(models.Model):
    """Lead/applicant for admissions funnel. ENROLLED stage triggers creation of StudentProfile (same tenant)."""

    class Stage(models.TextChoices):
        LEAD = "LEAD", "Lead"
        APPLIED = "APPLIED", "Applied"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"
        ENROLLED = "ENROLLED", "Enrolled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="applicants",
    )
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    email = models.EmailField()
    lead_source = models.CharField(max_length=80, blank=True)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.LEAD)
    yield_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="AI/rule-based probability of enrollment (0–100).",
    )
    assigned_recruiter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_applicants",
    )
    extra_data = models.JSONField(default=dict, blank=True)
    # First-class offline idempotency anchor (DB-enforced via Meta constraint).
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)
    # v4.00.34: country-aware exam-score capture.
    exam_scores = models.JSONField(
        default=dict, blank=True,
        help_text="Per-subject scores keyed by schema subject code, e.g. {'english': 'A1', 'math': 'B2'}.",
    )
    exam_schema_code = models.CharField(
        max_length=40, blank=True,
        help_text="Slug of the apps.siteconfig._admissions_intake_schemas entry used.",
    )
    exam_marker = models.CharField(
        max_length=80, blank=True,
        help_text="Display label for the exam (WASSCE / KCSE / Thanaweya / Baccalauréat …).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Applicant"
        verbose_name_plural = "Applicants"
        indexes = [
            models.Index(fields=["school", "stage"]),
            models.Index(fields=["email", "school"]),
            models.Index(fields=["school", "exam_schema_code"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_applicant_school_offline_id",
            ),
        ]

    def __str__(self):
        return f"{self.last_name}, {self.first_name} ({self.stage})"


class RetentionAlert(models.Model):
    """At-risk student alert for advisor dashboard. Sovereign AI: analysis_summary must be human-readable."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="retention_alerts",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="retention_alerts",
    )
    risk_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="0–100 risk score",
    )
    alert_level = models.CharField(
        max_length=20, default="MEDIUM"
    )  # LOW, MEDIUM, HIGH, CRITICAL
    analysis_summary = models.TextField(
        blank=True,
        help_text="Human-readable explanation (Sovereign AI: why this flag was raised).",
    )
    primary_reason = models.CharField(max_length=255, blank=True)
    recommended_action = models.CharField(max_length=255, blank=True)
    is_resolved = models.BooleanField(default=False)
    intervention_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-risk_score", "-created_at"]
        verbose_name = "Retention alert"
        verbose_name_plural = "Retention alerts"
        indexes = [models.Index(fields=["school", "is_resolved"])]

    def __str__(self):
        return f"{self.student} — risk {self.risk_score} ({self.alert_level})"


# -----------------------------------------------------------------------------
# Student Passport / Identity Vault (lifetime identity, verified docs, cross-school)
# -----------------------------------------------------------------------------


class StudentPassport(models.Model):
    """
    Lifetime student identity that survives school churn. One passport can link
    to many StudentProfiles (different schools). GUID for portability; optional
    owner (User) for login to view/manage; verified documents attached via
    PassportDocument; invite schools via PassportSchoolInvite.
    """

    guid = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, db_index=True
    )
    owner = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_passport",
        help_text=_("User account that owns this passport (student or parent)."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("Student passport")
        verbose_name_plural = _("Student passports")

    def __str__(self):
        return str(self.guid)


class PassportDocument(models.Model):
    """Verified document (transcript, certificate, diploma) attached to a passport."""

    class DocType(models.TextChoices):
        TRANSCRIPT = "TRANSCRIPT", _("Transcript")
        CERTIFICATE = "CERTIFICATE", _("Certificate")
        DIPLOMA = "DIPLOMA", _("Diploma")
        OTHER = "OTHER", _("Other")

    passport = models.ForeignKey(
        StudentPassport,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(
        max_length=20, choices=DocType.choices, default=DocType.OTHER
    )
    title = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to=_passport_doc_upload_to, blank=True, null=True)
    file_url = models.URLField(blank=True, help_text=_("External URL if not uploaded."))
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by_school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("School that verified this document."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Passport document")
        verbose_name_plural = _("Passport documents")

    def __str__(self):
        return f"{self.get_document_type_display()} — {self.title or self.pk}"


class PassportSchoolInvite(models.Model):
    """Invite a school to view this passport (read-only). Token-based link."""

    passport = models.ForeignKey(
        StudentPassport,
        on_delete=models.CASCADE,
        related_name="school_invites",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="passport_invites",
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    token = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, db_index=True
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("passport", "school")]
        ordering = ["-created_at"]
        verbose_name = _("Passport school invite")
        verbose_name_plural = _("Passport school invites")

    def __str__(self):
        return f"{self.passport_id} → {self.school_id} ({self.token})"


# -----------------------------------------------------------------------------
# Apprenticeship: employer portal (verify apprentice hours, confirm on-site)
# -----------------------------------------------------------------------------


class ApprenticePlacement(models.Model):
    """Links an employer (User with role EMPLOYER) to a student for on-site hours verification."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="apprentice_placements",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="apprentice_placements",
    )
    employer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="apprentice_placements",
        help_text=_("User with EMPLOYER role who can confirm hours."),
    )
    confirmed_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text=_("Total on-site hours confirmed by this employer."),
    )
    last_confirmed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("school", "student", "employer")]
        ordering = ["-updated_at"]
        verbose_name = _("Apprentice placement")
        verbose_name_plural = _("Apprentice placements")

    def __str__(self):
        return f"{self.employer} — {self.student} @ {self.school}"


class EmployerProfile(models.Model):
    """Optional profile for users with EMPLOYER role: company name and school link (Plan XI)."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="employer_profile",
        help_text=_("User with role EMPLOYER."),
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="employer_profiles",
        null=True,
        blank=True,
    )
    company_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company_name"]
        verbose_name = _("Employer profile")
        verbose_name_plural = _("Employer profiles")

    def __str__(self):
        return self.company_name or str(self.user)


# -----------------------------------------------------------------------------
# Vocational certifications (industry licenses, expiry tracking, watchdog)
# -----------------------------------------------------------------------------


class VocationalCertification(models.Model):
    """
    Industry or vocational certification (e.g. FAA, Nursing, CompTIA).
    expiry_date drives "Certification Watchdog" alerts (e.g. expiring in 30 days).
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="vocational_certifications",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="vocational_certifications",
    )
    name = models.CharField(
        max_length=255, help_text=_("e.g. FAA Medical, Nursing License")
    )
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(
        null=True, blank=True, help_text=_("When set, used for expiry alerts")
    )
    issuing_body = models.CharField(max_length=255, blank=True)
    credential_id = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-expiry_date", "name"]
        verbose_name = _("Vocational certification")
        verbose_name_plural = _("Vocational certifications")

    def __str__(self):
        return f"{self.student} — {self.name} (expires {self.expiry_date})"


# -----------------------------------------------------------------------------
# Tenant audit log (Part 4.6) — INSERT-only; trigger or app-level writes
# -----------------------------------------------------------------------------


class TenantAuditLog(models.Model):
    """
    Per-tenant audit trail (one table per tenant schema). INSERT-only; use DB
    permissions to revoke UPDATE/DELETE. Who/What/Where/When/Why + correlation_id.
    Populated by app-level logging or PostgreSQL triggers (see docs/AUDIT_TRAIL_TRIGGER_BASED.md).
    """

    table_name = models.CharField(max_length=128)
    record_id = models.CharField(max_length=255, blank=True)
    action = models.CharField(
        max_length=16,
        choices=[("INSERT", "INSERT"), ("UPDATE", "UPDATE"), ("DELETE", "DELETE")],
    )
    old_values = models.JSONField(
        default=dict, blank=True
    )  # PII masking applied before write
    new_values = models.JSONField(default=dict, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    request_meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-changed_at"]
        verbose_name = _("Audit log entry")
        verbose_name_plural = _("Audit log")


# North Star SLICE 13 — auxiliary passport models (canonical StudentPassport is defined above)
from .student_passport_models import StudentPassportMembership, TranscriptVaultItem  # noqa: E402,F401


class SpecialEducationPlan(models.Model):
    """Education-system phase 2 (2026-05-11): per-student IEP / 504 plan record.

    US K-12 unlock requirement. Schools that take public-district contracts
    must surface a Special Education plan for every student who has one, with
    primary disability code, accommodations, and review schedule. This is the
    canonical row; the full IEP document (PDF) is attached separately.

    Privacy: tenant-scoped via ForeignKey to school; admin + downstream views
    are gated to staff with ``people.view_specialeducationplan`` (separate
    permission from regular StudentProfile read).
    """

    class PlanType(models.TextChoices):
        IEP = "IEP", _("IEP (Individualized Education Plan)")
        FIVE_OH_FOUR = "504", _("504 Plan")
        GIFTED = "GIFTED", _("Gifted / advanced learner plan")
        ELL = "ELL", _("English-language learner plan")
        OTHER = "OTHER", _("Other (note required)")

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        ACTIVE = "ACTIVE", _("Active")
        UNDER_REVIEW = "UNDER_REVIEW", _("Under review")
        EXPIRED = "EXPIRED", _("Expired")
        WITHDRAWN = "WITHDRAWN", _("Withdrawn")

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="special_education_plans",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="special_education_plans",
    )
    plan_type = models.CharField(max_length=16, choices=PlanType.choices, default=PlanType.IEP)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    primary_disability = models.CharField(
        max_length=128,
        blank=True,
        help_text=_("IDEA primary disability category, where applicable."),
    )
    accommodations = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Free-text accommodations list (extra time, scribe, etc.)."),
    )
    goals = models.TextField(
        blank=True,
        help_text=_("Measurable annual goals — kept brief; full plan PDF attached separately."),
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    next_review_at = models.DateField(
        null=True,
        blank=True,
        help_text=_("Statutory review deadline; surfaces in SLA queues."),
    )
    case_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="special_education_plans_managed",
        help_text=_("Special-ed coordinator or counselor owning this plan."),
    )
    plan_document = models.FileField(
        upload_to=tenant_upload_to_special_education_plan,
        null=True,
        blank=True,
        help_text=_("Signed IEP / 504 PDF (FERPA-sensitive)."),
    )
    parent_consent_on_file = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="special_education_plans_created",
    )

    class Meta:
        ordering = ["-effective_from", "-id"]
        verbose_name = _("Special Education plan")
        verbose_name_plural = _("Special Education plans")
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["student", "-effective_from"]),
            models.Index(fields=["next_review_at"]),
        ]

    def __str__(self):
        return f"{self.get_plan_type_display()} — {self.student_id}"


class StudentNote(models.Model):
    """
    Teacher/staff narrative captured online or via offline NOTES_REPORT sync.
    Scoped by school; optional student link for per-learner sticky notes.
    """

    class Kind(models.TextChoices):
        NOTE = "note", _("Note")
        REPORT = "report", _("Report")
        QUICK_CAPTURE = "quick_capture", _("Quick capture")

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="student_notes",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="staff_notes",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_notes_authored",
    )
    kind = models.CharField(
        max_length=48,
        choices=Kind.choices,
        default=Kind.NOTE,
    )
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    client_offline_id = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("Idempotency key from offline queue payload."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = _("Student note")
        verbose_name_plural = _("Student notes")
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["student", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=models.Q(client_offline_id__gt=""),
                name="people_studentnote_school_client_offline_uniq",
            ),
        ]

    def __str__(self):
        label = self.title or self.body[:48]
        return f"{self.get_kind_display()}: {label}"


from apps.people.staff_compliance import StaffComplianceRecord  # noqa: E402,F401
from apps.people.models_transfer import TransferCase, TransferStateError  # noqa: E402,F401
from apps.people.models_transfer_consent import (  # noqa: E402,F401
    TransferConsent,
    TransferConsentDecision,
    TransferConsentError,
)
from apps.people.models_merge import (  # noqa: E402,F401
    MergeStateError,
    RecordMergeOperation,
)
from apps.people.models_school_batch import (  # noqa: E402,F401
    BatchStateError,
    SchoolTransferBatch,
)
