from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.apps import apps as django_apps
from django.utils.translation import gettext_lazy as _

import re
import uuid

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Specialty, Department, Term


class TeacherProfile(models.Model):
    # Phase 4: Enable audit logging for this model (teacher record changes)
    audit_enabled = True

    class DashboardView(models.TextChoices):
        OVERVIEW = "OVERVIEW", "Overview"
        FINANCE = "FINANCE", "Finances"
        ACADEMICS = "ACADEMICS", "Academics"
        ATTENDANCE = "ATTENDANCE", "Attendance"

    staff_id = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    profile_photo = models.ImageField(upload_to="profiles/teachers/", blank=True, null=True)
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
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
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
    salary_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_cap = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    next_pay_date = models.DateField(null=True, blank=True)
    paystub_notes = models.TextField(blank=True)

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

    def suggested_dashboard_view(self) -> str:
        """
        Suggest a dashboard based on position/role keywords.
        """
        title = (self.position_title or "").lower()
        if any(k in title for k in ["finance", "hr", "bursar"]):
            return self.DashboardView.FINANCE
        if any(k in title for k in ["discipline", "attendance", "pastoral"]):
            return self.DashboardView.ATTENDANCE
        if any(k in title for k in ["principal", "director", "dean", "head", "vice principal"]):
            return self.DashboardView.OVERVIEW
        return self.default_dashboard_view or self.DashboardView.OVERVIEW

    def save(self, *args, **kwargs):
        # Only auto-adjust if a specific default hasn't been chosen yet.
        if self.position_title and self.default_dashboard_view == self.DashboardView.OVERVIEW:
            suggested = self.suggested_dashboard_view()
            if suggested != self.default_dashboard_view:
                self.default_dashboard_view = suggested
        super().save(*args, **kwargs)

    def clean(self):
        # Ensure the linked user is a teacher-aligned role
        allowed_roles = {
            User.Role.TEACHER,
            getattr(User.Role, "DEPT_LEAD", User.Role.TEACHER),
            getattr(User.Role, "LEADERSHIP", User.Role.TEACHER),
        }
        if self.user and self.user.role not in allowed_roles:
            raise ValidationError("TeacherProfile user must have a teacher or department-lead role")

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}"


class TeacherPayRecord(models.Model):
    class RecordType(models.TextChoices):
        PAY = "PAY", "Pay"
        RAISE = "RAISE", "Raise/Stipend"
        BONUS = "BONUS", "Bonus"

    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name="pay_records")
    record_type = models.CharField(max_length=12, choices=RecordType.choices, default=RecordType.PAY)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_pay_records")
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

    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name="leave_requests")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_leave_requests")
    decision_notes = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Leave {self.teacher} {self.start_date} -> {self.end_date} ({self.status})"


class TeacherAttendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"
        LATE = "LATE", "Late"
        ON_LEAVE = "ON_LEAVE", "On leave"

    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name="attendance_logs")
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("teacher", "date")
        ordering = ["-date", "-check_in"]

    def __str__(self):
        return f"{self.teacher} {self.date} ({self.status})"


class StudentProfile(models.Model):
    # Phase 4: Enable audit logging for this model (student record changes, grades tied to this)
    audit_enabled = True

    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
    )

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    student_code = models.CharField(max_length=50, unique=True, blank=True)
    admission_number = models.CharField(max_length=64, unique=True, blank=True, null=True)
    profile_photo = models.ImageField(upload_to="profiles/students/", blank=True, null=True)

    class Gender(models.TextChoices):
        MALE = "MALE", "Male"
        FEMALE = "FEMALE", "Female"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        NEW = "NEW", "New"
        RETURNING = "RETURNING", "Returning"
        PROBATION = "PROBATION", "Probation"
        ALUMNI = "ALUMNI", "Alumni"

    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, blank=True, choices=Status.choices)
    # Free-text code to store the joined term (now dynamic). Use portal form for choices.
    joined_term = models.CharField(max_length=20, blank=True)
    joined_date = models.DateField(null=True, blank=True)
    section = models.CharField(max_length=80, blank=True)
    parent_phone = models.CharField(max_length=50, blank=True)
    referral_code = models.CharField(max_length=80, blank=True)

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="students", null=True, blank=True)
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT, related_name="students", null=True, blank=True)
    specialty = models.ForeignKey(
        Specialty,
        on_delete=models.PROTECT,
        related_name="students",
        null=True,
        blank=True,
    )

    # Exam system fields (configurable for different countries)
    exam_candidate_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="National exam candidate number (e.g., GCE, WAEC, etc.)"
    )
    exam_center_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="Exam center code"
    )
    exam_system = models.CharField(
        max_length=50,
        blank=True,
        help_text="Exam system (e.g., GCE, WAEC, IB, etc.)"
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
        help_text="Soft delete timestamp - preserves grade history when student leaves"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students_created',
        help_text="User who created this student record"
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students_updated',
        help_text="User who last updated this student record"
    )

    class Meta:
        ordering = ["last_name", "first_name"]

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
    def generate_admission_number(
        cls,
        academic_year: AcademicYear,
        specialty: Specialty,
        classroom: Classroom,
    ) -> str:
        """
        Build YY + SCHOOLCODE + #### + SPEC + CLASS (no dashes, no trailing F).
        - YY: start year suffix from AcademicYear.name (first four digits -> last two)
        - SCHOOLCODE: from SiteSettings.school_code (default GIL)
        - ####: zero-padded sequence per academic year
        - SPEC: Specialty.code
        - CLASS: classroom segment (numeric tail or first two chars), digits only when available
        """
        SiteSettings = django_apps.get_model("siteconfig", "SiteSettings")
        settings = SiteSettings.get_solo()
        school_code = (settings.school_code or "GIL").upper()

        year_str = (academic_year.name or "")[:4]
        yy = year_str[-2:] if year_str and year_str[:4].isdigit() else "00"

        seq = cls.objects.filter(academic_year=academic_year).count() + 1
        seq_str = f"{seq:04d}"

        spec_segment = (specialty.code or "XX").upper()[:6] if specialty else "XX"
        class_segment = cls._class_segment(classroom)

        # Remove non-alphanumerics to keep the ID compact and numeric-friendly at the tail.
        spec_segment = re.sub(r"[^A-Z0-9]", "", spec_segment)
        class_segment = re.sub(r"[^A-Z0-9]", "", class_segment)

        return f"{yy}{school_code}{seq_str}{spec_segment}{class_segment}"

    def save(self, *args, **kwargs):
        # Auto-generate admission number when not provided, if enabled in SiteSettings.
        # Use _id checks to avoid related object descriptor errors when foreign keys
        # aren't set during tests.
        if getattr(self, "academic_year_id", None) and getattr(self, "specialty_id", None) and getattr(
            self, "classroom_id", None
        ):
            SiteSettings = django_apps.get_model("siteconfig", "SiteSettings")
            site_settings = SiteSettings.get_solo()
            mode = getattr(site_settings, "admission_number_mode", None)

            # Backwards-compatible default: allow auto-generation when admission number is blank.
            auto_modes = {
                getattr(SiteSettings.AdmissionNumberMode, "AUTO", "AUTO"),
                getattr(SiteSettings.AdmissionNumberMode, "AUTO_OR_MANUAL", "AUTO_OR_MANUAL"),
            }
            auto_allowed = (mode in auto_modes) or (mode is None)

            if auto_allowed and not self.admission_number:
                from apps.academics.models import AcademicYear, Classroom, Specialty

                # Resolve objects for generation
                year = AcademicYear.objects.get(id=self.academic_year_id)
                specialty = Specialty.objects.get(id=self.specialty_id)
                classroom = Classroom.objects.get(id=self.classroom_id)
                self.admission_number = self.generate_admission_number(
                    year,
                    specialty,
                    classroom,
                )
        if not self.student_code:
            self.student_code = self.admission_number or f"TEMP-{uuid.uuid4().hex[:8].upper()}"
        if not self.referral_code:
            self.referral_code = f"REF-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def clean(self):
        """
        Validate admission number format; keep editable but enforce structure.
        """
        if self.admission_number:
            # Use admission number pattern from SiteSettings when available,
            # falling back to the built-in YY + SCHOOL + #### + SPEC + CLASS pattern.
            SiteSettings = django_apps.get_model("siteconfig", "SiteSettings")
            site_settings = SiteSettings.get_solo()
            pattern = getattr(site_settings, "admission_number_pattern", "") or ""
            if not pattern:
                new_style = r"^\d{2}[A-Z0-9]{2,10}\d{4}[A-Z0-9]{2,6}[A-Z0-9]{1,4}$"
                legacy = r"^\d{2}-[A-Z0-9]{2,10}-\d{4}-[A-Z0-9]{2,6}-[A-Z0-9]{1,4}$"
                pattern = rf"({new_style}|{legacy})"
            if not re.match(pattern, self.admission_number):
                raise ValidationError(
                    {
                        "admission_number": _(
                            "Admission number must match YY + SCHOOL + #### + SPEC + CLASS (no dashes) or the legacy dashed format."
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

    guardian_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guardian_links")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="guardian_links")

    relationship = models.CharField(max_length=20, choices=Relationship.choices, default=Relationship.GUARDIAN)
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
        # Ensure the linked user is a PARENT
        if self.guardian_user and self.guardian_user.role != User.Role.PARENT:
            raise ValidationError("StudentGuardian guardian_user must have role=PARENT")

    def __str__(self):
        return f"{self.guardian_user.username} -> {self.student}"

# ========== NOTIFICATION PREFERENCES ==========

class NotificationPreference(models.Model):
    """Guardian notification settings per student."""
    
    CONTACT_METHOD_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('both', 'Email & SMS'),
        ('none', 'Opt Out'),
    ]
    
    DIGEST_CHOICES = [
        ('immediate', 'Immediately'),
        ('daily', 'Daily Digest at 6 PM'),
        ('weekly', 'Weekly Digest (Fri 6 PM)'),
    ]
    
    guardian = models.OneToOneField(
        StudentGuardian,
        on_delete=models.CASCADE,
        related_name='notification_preference'
    )
    
    # Grade publication
    grade_publication_method = models.CharField(
        max_length=20,
        choices=CONTACT_METHOD_CHOICES,
        default='both'
    )
    grade_publication_frequency = models.CharField(
        max_length=20,
        choices=DIGEST_CHOICES,
        default='immediate'
    )
    
    # Deadline reminders
    deadline_reminder_method = models.CharField(
        max_length=20,
        choices=CONTACT_METHOD_CHOICES,
        default='email'
    )
    deadline_reminder_enabled = models.BooleanField(default=True)
    
    # Teacher reminders (if guardian is also teacher)
    teacher_reminder_times = models.JSONField(default=list, blank=True)
    teacher_reminder_method = models.CharField(
        max_length=20,
        choices=CONTACT_METHOD_CHOICES,
        default='email'
    )
    
    class Meta:
        verbose_name_plural = 'Notification Preferences'
    
    def __str__(self):
        return f"Prefs for {self.guardian.guardian_user.get_full_name()}"


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
        return f"{self.student} – {self.item_label} ({self.academic_year.name}) – {status}"


class BadgeType(models.Model):
    """Configurable badge type (e.g. Syllabus Master, Honor Roll, Acting Principal)."""
    class Audience(models.TextChoices):
        STAFF = "STAFF", "Staff"
        STUDENT = "STUDENT", "Student"

    code = models.CharField(max_length=60, unique=True)
    label = models.CharField(max_length=120)
    audience = models.CharField(max_length=20, choices=Audience.choices, default=Audience.STAFF)
    criteria_rule = models.JSONField(default=dict, blank=True, help_text="Optional rule config (e.g. threshold, trigger).")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["audience", "code"]
        verbose_name = "Badge type"
        verbose_name_plural = "Badge types"

    def __str__(self):
        return f"{self.label} ({self.get_audience_display()})"


class Badge(models.Model):
    """Awarded badge (staff or student). Trigger-based; optional QR for verification."""
    badge_type = models.ForeignKey(BadgeType, on_delete=models.CASCADE, related_name="badges")
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
    expiry_at = models.DateTimeField(null=True, blank=True, help_text="When badge is automatically revoked (e.g. delegation end).")
    is_physical_printed = models.BooleanField(default=False)
    qr_data = models.CharField(max_length=255, blank=True, help_text="Signed token or payload for QR verification.")
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
