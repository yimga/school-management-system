from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

import hashlib
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
    # The trade/filiere a staff member teaches in. Cameroonian technical schools
    # publish this as the SPECIALTY column of their staff directory -- CARPENTRY
    # AND JOINERY, ELECTRICAL POWER SYSTEMS, FASHION DESIGN -- and until now a
    # TeacherProfile had nowhere to put it, so every staff import folded specialty
    # into ``department`` and lost the distinction. StudentProfile, Enrollment and
    # FeePlan all carry Specialty already; staff were the gap.
    #
    # SET_NULL rather than StudentProfile's PROTECT: retiring a filiere must not be
    # blocked by a teacher who once taught it, and a teacher with no specialty is a
    # normal state (the bursar, the driver, the security post).
    #
    # Because Specialty carries its own FK to Department, this field also makes the
    # derived cascade in apps.metadata.inline_edit real for staff: choosing a
    # specialty now implies its department, which is the rule the school asked for
    # and which the schema can answer without anyone configuring it.
    specialty = models.ForeignKey(
        Specialty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teachers",
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="teacher_profile"
    )
    is_active = models.BooleanField(default=True)
    # Duplicate-merge tombstone (Wave C): the retired duplicate points at the
    # surviving row. Without it the merge engine's idempotency guard
    # (`_resolve_pair`: refuse if `secondary.merged_into_id`) could never fire
    # for teachers, so an already-merged teacher could be merged again.
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_teacher_duplicates",
    )
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
        # A plan's staff cap refuses THIS hire, not the school's whole day.
        from apps.schools.plan_limits import enforce_enrolment_cap

        enforce_enrolment_cap(
            self, cap_field="max_staff", model=TeacherProfile, label="staff"
        )
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

    @staticmethod
    def eligible_user_roles():
        """Roles a TeacherProfile may be linked to. ONE definition, deliberately.

        clean() enforces this and the admin filters its user dropdown with it. When
        the two were separate the dropdown offered every user on the platform -- 24
        of them on a live school, 22 of which this same clean() then refused -- so
        the only way to discover a choice was invalid was to submit it.
        """
        return {
            User.Role.TEACHER,
            getattr(User.Role, "DEPT_LEAD", User.Role.TEACHER),
            getattr(User.Role, "LEADERSHIP", User.Role.TEACHER),
        }

    def clean(self):
        # Ensure the linked user is a teacher-aligned role
        allowed_roles = self.eligible_user_roles()
        # Guard on user_id (the raw FK column), NOT self.user: during a
        # TeacherCreateForm ModelForm _post_clean the instance is validated
        # BEFORE the view attaches the user, and accessing the OneToOne
        # descriptor with an unset id raises RelatedObjectDoesNotExist (an
        # uncaught 500, not a ValidationError). Matches the self.user_id guard
        # used elsewhere in this module.
        if self.user_id and self.user.role not in allowed_roles:
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
        """Issue the next admission number for this school-year, on THIS node.

        Shape comes from get_effective_policy(school)["admissions"], else the platform
        defaults in _get_admissions_policy. Placeholders: year_2digit, school_code,
        seq_4digit, spec_code, class_segment, node_code.

        The shape itself lives in ``identifier_policy_service.render_admission_number``,
        shared with the setup preview, because a format a school validates against has to
        be the format the school is given.
        """
        school = school or getattr(academic_year, "school", None)
        admissions = cls._get_admissions_policy(school)
        from apps.siteconfig.identifier_policy_service import (
            default_school_code_for,
            node_identifier_namespace,
            render_admission_number,
        )

        school_code = (
            admissions.get("school_code") or default_school_code_for(school)
        ).upper()
        # WHICH NODE is issuing this. Two nodes both mint from their own row count, so
        # without a mark that differs between them they eventually issue one number
        # twice -- and `student_code` defaults to it, is on the rail, and is per-school
        # unique, so the second copy to arrive is refused and that student never lands.
        node_code = node_identifier_namespace(school, policy=admissions)

        year_str = (academic_year.name or "")[:4]
        yy = year_str[-2:] if year_str and year_str[:4].isdigit() else "00"

        spec_segment = (specialty.code or "XX").upper()[:6] if specialty else "XX"
        class_segment = cls._class_segment(classroom)
        spec_segment = re.sub(r"[^A-Z0-9]", "", spec_segment)
        class_segment = re.sub(r"[^A-Z0-9]", "", class_segment)

        def _render(seq: int) -> str:
            return render_admission_number(
                admissions,
                year_2digit=yy,
                school_code=school_code,
                seq_4digit=f"{seq:04d}",
                spec_code=spec_segment,
                class_segment=class_segment,
                node_code=node_code,
            )

        if school is None:
            # No school means no counter to key, and no per-school uniqueness to defend.
            # This is a preview-shaped call, not an enrolment; give it the sample number
            # rather than allocating a real one nobody will use.
            return _render(1)

        # NOT `count() + 1`. A count goes DOWN when a row is deleted, so the next arrival
        # was handed a departed student's number, and two concurrent enrolments read the
        # same count and both believed they were issuing it. The counter row survives the
        # delete and is claimed under a lock.
        from apps.people.models_identifier_sequence import allocate_admission_seq

        # What must be unique is the rendered NUMBER, not the sequence -- two strategies
        # can map different sequences onto the same string. A school that has deleted
        # students has issued numbers above its row count, so a counter seeded from that
        # count can start on one somebody already holds.
        seq = allocate_admission_seq(
            school,
            academic_year,
            node_code,
            is_taken=lambda candidate: cls.objects.filter(
                school=school, admission_number=_render(candidate)
            ).exists(),
        )
        return _render(seq)

    def save(self, *args, **kwargs):
        # A plan's student cap refuses THIS enrolment, not the school's whole
        # day: attendance, report cards and fee collection keep working.
        from apps.schools.plan_limits import enforce_enrolment_cap

        enforce_enrolment_cap(
            self, cap_field="max_students", model=StudentProfile, label="student"
        )
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
            # A PLACEHOLDER THE TWO NODES CAN BOTH ARRIVE AT, when there is anything to
            # arrive at it FROM. `student_code` is on the rail and per-school unique, and
            # `apply_edge_inserts` upserts by `client_offline_id` -- so when one offline
            # row lands on both nodes, they are matched as ONE student and their codes
            # are compared. A random placeholder made that disagreement permanent and
            # unarbitrable: neither value is more right, and no later retry changes
            # either one.
            #
            # THE NODE MARK IS DELIBERATELY ABSENT FROM THE DERIVED FORM, which reads
            # like a regression and is the opposite. On an admission number the mark is
            # what stops two nodes issuing the same number, and removing it would undo
            # that. One row's placeholder has the inverse requirement -- the nodes must
            # land on the SAME string -- and stamping the local node in guarantees they
            # never do. The two identifiers want opposite things from the same mark.
            #
            # 64 bits of the digest: the column allows 50 characters and this needs 21,
            # so there is no reason to shave it down to where a collision between two
            # offline ids in one school stops being unthinkable -- that collision would
            # surface as a refused enrolment, not a wrong number.
            coid = (getattr(self, "client_offline_id", "") or "").strip()
            if self.admission_number:
                self.student_code = self.admission_number
            elif coid:
                self.student_code = "TEMP-%s" % (
                    hashlib.sha256(coid.encode("utf-8")).hexdigest()[:16].upper(),
                )
            else:
                # Nothing to converge WITH, so the code is local by nature and the mark
                # earns its place again: an operator holding two of these needs to know
                # which node invented which.
                from apps.siteconfig.identifier_policy_service import (
                    node_identifier_namespace,
                )

                self.student_code = "TEMP-%s-%s" % (
                    node_identifier_namespace(getattr(self, "school", None)),
                    uuid.uuid4().hex[:8].upper(),
                )
        if not self.referral_code:
            self.referral_code = f"REF-{uuid.uuid4().hex[:6].upper()}"
        from apps.people.student_search_index import build_student_search_index

        self.search_index = build_student_search_index(self)
        super().save(*args, **kwargs)

    def clean(self):
        """Validate admission number format from policy (admission_number_pattern)."""
        if self.admission_number:
            # The school this row belongs to, falling back to its own FK: reading
            # the policy for the WRONG school hands back platform defaults, and the
            # number was rendered from the school's own shape.
            school = (
                getattr(self.academic_year, "school", None)
                if getattr(self, "academic_year", None)
                else None
            ) or getattr(self, "school", None)
            admissions = self._get_admissions_policy(school)
            # Derived from the SAME template/strategy the number was rendered from.
            # This used to hardcode the FULL shape whenever a school had set no
            # explicit pattern, so a school on TEMPLATE / YEAR_SEQ / SEQ_ONLY had its
            # own auto-generated number refused and "leave blank to auto-generate"
            # could never succeed.
            from apps.siteconfig.identifier_policy_service import (
                admission_number_pattern_for,
            )

            pattern = admission_number_pattern_for(admissions)
            if not re.match(pattern, self.admission_number):
                raise ValidationError(
                    {
                        "admission_number": _(
                            "Admission number must match the required format (YY + SCHOOL + #### + SPEC + CLASS or legacy dashed)."
                        )
                    }
                )
        super().clean()

    # ---- Enrollment derivation (2.2) -------------------------------------
    # ``classroom``/``academic_year`` above are now a synchronised PROJECTION of
    # the active Enrollment, kept because ~180 call sites read them. New code
    # should read these properties instead: they survive promotion, where the
    # raw fields only ever hold the CURRENT year.

    @property
    def current_enrollment(self):
        """The open Enrollment, or None. At most one exists (DB constraint)."""
        return (
            self.enrollments.filter(status=Enrollment.Status.ACTIVE)
            .select_related("classroom", "academic_year", "specialty")
            .order_by("-entry_date", "-id")
            .first()
        )

    @property
    def current_classroom(self):
        """Class derived from the active enrollment; legacy field is the fallback.

        The fallback is deliberate and load-bearing: a tenant whose backfill has
        not run yet, or a student created by a path that has not been moved onto
        Enrollment, must still resolve a class rather than silently read None.
        """
        enrollment = self.current_enrollment
        if enrollment is not None and enrollment.classroom_id:
            return enrollment.classroom
        return self.classroom

    @property
    def current_academic_year(self):
        enrollment = self.current_enrollment
        if enrollment is not None:
            return enrollment.academic_year
        return self.academic_year

    def enrollment_for_year(self, academic_year):
        """This student's enrollment in a GIVEN year — the history lookup."""
        return (
            self.enrollments.filter(academic_year=academic_year)
            .order_by("-entry_date", "-id")
            .first()
        )

    def enrollment_history(self):
        """Chronological placements, oldest first. Basis of a transcript."""
        return self.enrollments.select_related(
            "classroom", "academic_year"
        ).order_by("academic_year__start_date", "entry_date", "id")


# Backwards-compatibility alias
# Older code/tests import `Student` from apps.people.models — keep this alias to avoid ImportError
Student = StudentProfile


class EnrollmentQuerySet(models.QuerySet):
    def active(self):
        """The open enrollment — the row the student's CURRENT class derives from."""
        return self.filter(status=Enrollment.Status.ACTIVE)

    def closed(self):
        return self.exclude(status=Enrollment.Status.ACTIVE)

    def for_year(self, academic_year):
        return self.filter(academic_year=academic_year)

    def history(self):
        """Chronological academic history (oldest first) — transcripts, analytics."""
        return self.order_by("academic_year__start_date", "entry_date", "id")


class Enrollment(models.Model):
    """One student's placement in one class for one academic year.

    THE POINT OF THIS TABLE. Before it existed a student's class lived only in
    ``StudentProfile.classroom``/``.academic_year``, so year-end promotion was a
    destructive ``UPDATE``: last year's placement was overwritten and lost. Three
    things were therefore impossible — academic history/transcripts, *repeating a
    year* (nothing could say "Grade 5 in 2025 AND Grade 5 again in 2026"), and any
    longitudinal or statutory return that needs a per-year roll.

    Promotion now OPENS a new row and CLOSES the prior one. Nothing is overwritten.

    COMPATIBILITY. ``StudentProfile.classroom``/``.academic_year`` remain as a
    synchronised PROJECTION of the active enrollment (see ``sync_student_row``),
    because ~180 readers across 20 apps still read them. They are no longer the
    source of truth; ``StudentProfile.current_classroom`` is.

    COUNTRY NEUTRALITY. ``Outcome`` is the union of what school systems actually
    record worldwide, not one country's set: a US/UK grade-repeat, a French
    *redoublement*, an Indian "compartment"/conditional pass, a graduation, a
    transfer out, a withdrawal. Local wording goes in ``outcome_reason``; the
    stored code stays comparable across tenants so cross-country analytics work.
    """

    audit_enabled = True

    class Status(models.TextChoices):
        """Lifecycle of the ENROLLMENT ROW (not the academic result)."""

        ACTIVE = "ACTIVE", _("Active")
        COMPLETED = "COMPLETED", _("Completed")
        WITHDRAWN = "WITHDRAWN", _("Withdrawn")
        CANCELLED = "CANCELLED", _("Cancelled")

    class Outcome(models.TextChoices):
        """How the year ENDED for this student. Blank until the year closes."""

        PROMOTED = "PROMOTED", _("Promoted")
        RETAINED = "RETAINED", _("Retained (repeating the year)")
        CONDITIONALLY_PROMOTED = (
            "CONDITIONALLY_PROMOTED",
            _("Conditionally promoted"),
        )
        TRANSFERRED_OUT = "TRANSFERRED_OUT", _("Transferred out")
        GRADUATED = "GRADUATED", _("Graduated")
        WITHDRAWN = "WITHDRAWN", _("Withdrawn")
        # A school's decision, not a family's. Kept SEPARATE from WITHDRAWN on
        # purpose: the two look alike in a list and behave differently
        # everywhere it matters -- re-admission, a transfer certificate, a
        # ministry return, and what a school has to be able to show years later
        # if the decision is challenged. Folding an expulsion into "withdrawn"
        # loses the distinction precisely where it is needed.
        EXPELLED = "EXPELLED", _("Expelled (dismissed by the school)")

    #: Outcomes that keep the student in the SAME grade next year.
    RETENTION_OUTCOMES = frozenset({Outcome.RETAINED})
    #: Outcomes that move the student on to the next grade.
    ADVANCING_OUTCOMES = frozenset(
        {Outcome.PROMOTED, Outcome.CONDITIONALLY_PROMOTED}
    )
    #: Outcomes that end the student's presence at this school.
    EXIT_OUTCOMES = frozenset(
        {
            Outcome.GRADUATED,
            Outcome.TRANSFERRED_OUT,
            Outcome.WITHDRAWN,
            Outcome.EXPELLED,
        }
    )
    #: Exits the SCHOOL decided, not the family. A narrower set inside
    #: EXIT_OUTCOMES, so "did this student leave" and "was this student made to
    #: leave" are two different questions with two different answers -- which is
    #: the whole reason EXPELLED is not a label on WITHDRAWN.
    INVOLUNTARY_EXIT_OUTCOMES = frozenset({Outcome.EXPELLED})

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="enrollments",
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="enrollments",
    )
    specialty = models.ForeignKey(
        Specialty,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="enrollments",
    )
    section = models.CharField(max_length=80, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    entry_date = models.DateField(null=True, blank=True)
    exit_date = models.DateField(null=True, blank=True)

    outcome = models.CharField(
        max_length=32,
        choices=Outcome.choices,
        blank=True,
        default="",
        db_index=True,
        help_text=_(
            "How the year ended. Blank while the year is still running."
        ),
    )
    outcome_reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_(
            "Free text for the school's own wording or the condition attached "
            "to a conditional promotion. Never parsed."
        ),
    )
    outcome_recorded_at = models.DateTimeField(null=True, blank=True)
    #: The average the outcome was decided on — evidence, so a contested
    #: retention can be re-checked years later without re-running grading.
    decision_average = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    #: The enrollment this one succeeds. Makes the history a walkable chain.
    previous_enrollment = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="next_enrollments",
    )

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    objects = EnrollmentQuerySet.as_manager()

    class Meta:
        ordering = ["-entry_date", "-id"]
        indexes = [
            models.Index(fields=["school", "academic_year"]),
            models.Index(fields=["student", "academic_year"]),
            models.Index(fields=["classroom", "status"]),
        ]
        constraints = [
            # Exactly one OPEN enrollment per student. This is what makes
            # "current class" a well-defined derivation rather than a guess,
            # and it is why promotion MUST close the prior row before opening
            # the next one instead of overwriting a field.
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(status="ACTIVE"),
                name="people_enrollment_one_active_per_student",
            ),
        ]

    def __str__(self):
        where = self.classroom.name if self.classroom_id else "unplaced"
        return f"{self.student_id} @ {where} ({self.academic_year_id})"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    def clean(self):
        """Reject an impossible enrollment window.

        An enrollment cannot end before it began. The dates are otherwise
        unvalidated (both nullable), so a transposed ``entry_date``/``exit_date``
        — a data-entry slip or a caller passing them the wrong way round — would
        silently produce a negative-length placement that every downstream date
        arithmetic then reads as garbage. Enforced at ``clean()`` (called by the
        create entrypoints via ``full_clean``) rather than a DB ``CheckConstraint``
        so it needs no migration and cannot fail a fresh migrate on legacy rows.
        """
        super().clean()
        if (
            self.entry_date is not None
            and self.exit_date is not None
            and self.entry_date > self.exit_date
        ):
            raise ValidationError(
                {
                    "exit_date": _(
                        "Exit date cannot be earlier than the entry date."
                    )
                }
            )

    def save(self, *args, **kwargs):
        sync_student = kwargs.pop("sync_student", True)
        if self.school_id is None and self.student_id:
            self.school_id = getattr(self.student, "school_id", None)
        if self.outcome and self.outcome_recorded_at is None:
            self.outcome_recorded_at = timezone.now()
        super().save(*args, **kwargs)
        if sync_student and self.status == self.Status.ACTIVE:
            self.sync_student_row()

    def sync_student_row(self) -> bool:
        """Project this (active) enrollment onto the legacy student-row fields.

        The student row is a CACHE of the active enrollment, kept so that the
        ~180 existing readers of ``student.classroom`` keep working unchanged.
        Returns True when it actually wrote.
        """
        if self.status != self.Status.ACTIVE or not self.student_id:
            return False
        student = self.student
        changed = []
        if student.academic_year_id != self.academic_year_id:
            student.academic_year_id = self.academic_year_id
            changed.append("academic_year")
        if student.classroom_id != self.classroom_id:
            student.classroom_id = self.classroom_id
            changed.append("classroom")
        if self.specialty_id and student.specialty_id != self.specialty_id:
            student.specialty_id = self.specialty_id
            changed.append("specialty")
        if not changed:
            return False
        student.save(update_fields=changed)
        return True

    def close(
        self,
        outcome: str,
        *,
        exit_date=None,
        status: str | None = None,
        reason: str = "",
        decision_average=None,
    ) -> "Enrollment":
        """Close this enrollment with a recorded outcome. Never deletes."""
        if outcome not in dict(self.Outcome.choices):
            raise ValidationError(f"Unknown enrollment outcome: {outcome!r}")
        # An expulsion with no recorded ground is a record the school cannot
        # defend, to a parent or to a ministry, and the moment it is written is
        # the only moment anyone still knows why. Every other outcome is
        # derivable from marks or is the family's own decision; this one is
        # neither, so it is the one that must carry its reason.
        if outcome == self.Outcome.EXPELLED and not (
            reason or self.outcome_reason
        ):
            raise ValidationError(
                {
                    "outcome_reason": _(
                        "An expulsion must record the ground for it."
                    )
                }
            )
        self.outcome = outcome
        self.outcome_reason = reason or self.outcome_reason
        self.outcome_recorded_at = timezone.now()
        if decision_average is not None:
            self.decision_average = decision_average
        self.exit_date = exit_date or self.exit_date or timezone.now().date()
        if status is None:
            # The ROW's lifecycle, not the academic result: a year that
            # ended early -- for any reason, the school's or the family's --
            # leaves the enrollment WITHDRAWN rather than COMPLETED.
            status = (
                self.Status.WITHDRAWN
                if outcome
                in (
                    self.Outcome.WITHDRAWN,
                    self.Outcome.TRANSFERRED_OUT,
                    self.Outcome.EXPELLED,
                )
                else self.Status.COMPLETED
            )
        self.status = status
        # sync_student=False: a CLOSED enrollment must not touch the student
        # row. The successor enrollment owns that projection.
        self.save(sync_student=False)
        return self


class StudentGuardianQuerySet(models.QuerySet):
    def active(self):
        """Links that are still live — excludes merge-retired duplicates.

        A guardian-record merge soft-retires the losing link (``is_active=False``
        + ``merged_into``). Notification recipient builders and access checks
        call this so a retired duplicate is never notified or granted access a
        second time; a split/unmerge flips ``is_active`` back.
        """
        return self.filter(is_active=True)


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
    # Duplicate-merge tombstone (Wave C / guardian). A guardian-record merge
    # soft-retires the losing link instead of deleting it — its inbound
    # financial FKs (InvoicePayerShare CASCADE, ReferralReward PROTECT) are
    # re-pointed onto the surviving link first, then this row is retired.
    # Reads that notify or grant access use `.active()`; a split/unmerge flips
    # is_active back. Retiring was previously a NO-OP (this model had neither
    # field) while the merge FSM still reported APPLIED, so the duplicate stayed
    # live and the guardian was notified twice.
    is_active = models.BooleanField(default=True)
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_guardian_duplicates",
    )
    # Tenant ownership (2026-09-03). The link is SCHOOL data even though it names
    # a login: the edge sync rail scopes every entity by school, and this model
    # had no school column, so guardian contact edits made offline could never
    # ride. Nullable for old rows; save() aligns it from the student, the same
    # rule academics.Incident applies.
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    # Edge-sync contract, same shape as every rail entity. The entity is
    # INSERT-HELD (see _INSERT_HELD_ENTITIES): updates to an existing link
    # converge two-way, but creating one requires the accounts.User it names,
    # and minting a login that grants access to a child's records is an
    # authentication decision the rail must not make.
    updated_at = models.DateTimeField(auto_now=True, null=True)
    client_offline_id = models.CharField(
        max_length=128, blank=True, default="", db_index=True
    )

    objects = StudentGuardianQuerySet.as_manager()

    class Meta:
        unique_together = ("guardian_user", "student")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_studentguardian_school_offline_id",
            ),
        ]

    def save(self, *args, **kwargs):
        # Keep tenant ownership aligned with the student, mirroring
        # academics.Incident.save(): a link whose school stays NULL is invisible
        # to the school-scoped delta builder forever.
        if self.student_id and not self.school_id:
            self.school_id = getattr(self.student, "school_id", None)
        super().save(*args, **kwargs)

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
from apps.people.models_identifier_sequence import (  # noqa: E402,F401
    AdmissionNumberSequence,
    allocate_admission_seq,
)
from apps.people.models_provisioning import (  # noqa: E402,F401
    ProvisioningRequest,
)
