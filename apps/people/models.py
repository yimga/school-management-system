from django.db import models
from django.core.exceptions import ValidationError
from django.apps import apps as django_apps

import re
import uuid

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Specialty, Department


class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
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
    pay_grade = models.CharField(max_length=50, blank=True)
    salary_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_cap = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

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

    def clean(self):
        # Ensure the linked user is a TEACHER
        if self.user and self.user.role != User.Role.TEACHER:
            raise ValidationError("TeacherProfile user must have role=TEACHER")

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}"


class StudentProfile(models.Model):
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    student_code = models.CharField(max_length=50, unique=True, blank=True)
    admission_number = models.CharField(max_length=64, unique=True, blank=True, null=True)
    profile_photo = models.ImageField(upload_to="profiles/students/", blank=True, null=True)

    gender = models.CharField(max_length=10, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, blank=True)  # NEW | OLD
    joined_term = models.CharField(max_length=20, blank=True)
    joined_date = models.DateField(null=True, blank=True)
    section = models.CharField(max_length=80, blank=True)
    parent_phone = models.CharField(max_length=50, blank=True)
    referral_code = models.CharField(max_length=80, blank=True)

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="students")
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT, related_name="students")
    specialty = models.ForeignKey(Specialty, on_delete=models.PROTECT, related_name="students")

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.student_code})"

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
        Build YY-SCHOOLCODE-####-SPEC-CLASS.
        - YY: start year suffix from AcademicYear.name (first four digits -> last two)
        - SCHOOLCODE: from SiteSettings.school_code (default GIL)
        - ####: zero-padded sequence per academic year
        - SPEC: Specialty.code
        - CLASS: classroom segment (numeric tail or first two chars)
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

        return f"{yy}-{school_code}-{seq_str}-{spec_segment}-{class_segment}"

    def save(self, *args, **kwargs):
        if not self.admission_number and self.academic_year and self.specialty and self.classroom:
            self.admission_number = self.generate_admission_number(
                self.academic_year,
                self.specialty,
                self.classroom,
            )
        if not self.student_code:
            self.student_code = self.admission_number or f"TEMP-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


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
