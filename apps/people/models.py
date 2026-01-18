from django.db import models
from django.core.exceptions import ValidationError

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
    student_code = models.CharField(max_length=50, unique=True)
    profile_photo = models.ImageField(upload_to="profiles/students/", blank=True, null=True)

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="students")
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT, related_name="students")
    specialty = models.ForeignKey(Specialty, on_delete=models.PROTECT, related_name="students")

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.student_code})"


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
