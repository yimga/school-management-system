from django.db import models


class AcademicYear(models.Model):
    name = models.CharField(max_length=50)  # e.g. "2025/2026"
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


class Term(models.Model):
    class Name(models.TextChoices):
        FIRST = "FIRST", "First"
        SECOND = "SECOND", "Second"
        THIRD = "THIRD", "Third"

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=10, choices=Name.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        unique_together = ("academic_year", "name")
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.academic_year} - {self.get_name_display()}"


class Department(models.Model):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Specialty(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="specialties")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ClassRoom(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="classes")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Subject(models.Model):
    class Category(models.TextChoices):
        GENERAL = "GENERAL", "General"
        PROFESSIONAL = "PROFESSIONAL", "Professional"
        OTHER = "OTHER", "Other"

    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SubjectAssignment(models.Model):
    """
    Connects:
    AcademicYear + Term + ClassRoom + Specialty + Subject + Coefficient
    This is what teachers get assigned to, and what evaluations (marks) point to later.
    """
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="subject_assignments")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="subject_assignments")
    classroom = models.ForeignKey(ClassRoom, on_delete=models.PROTECT, related_name="subject_assignments")
    specialty = models.ForeignKey(Specialty, on_delete=models.PROTECT, related_name="subject_assignments")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="subject_assignments")
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        unique_together = ("academic_year", "term", "classroom", "specialty", "subject")
        ordering = ["classroom__name", "specialty__name", "subject__name"]

    def __str__(self):
        return f"{self.academic_year} | {self.term.get_name_display()} | {self.classroom} | {self.specialty} | {self.subject} (coef {self.coefficient})"

