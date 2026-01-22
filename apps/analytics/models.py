from django.db import models
from django.utils import timezone

from apps.academics.models import AcademicYear, Term, Classroom


class GradingDeadline(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="grading_deadlines",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="grading_deadlines",
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="grading_deadlines",
    )
    deadline_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("academic_year", "term", "classroom")
        ordering = ["-deadline_at"]

    def __str__(self) -> str:
        scope = self.classroom.name if self.classroom else "Whole school"
        date_label = timezone.localtime(self.deadline_at).strftime("%Y-%m-%d %H:%M")
        return f"{self.academic_year} {self.term.get_name_display()} - {scope}: {date_label}"

# ========== GRADE IMPORT JOB TRACKING ==========

class GradeImportJob(models.Model):
    """Tracks a single bulk grade import session."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('validating', 'Validating'),
        ('preview', 'Preview Ready'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Completed'),
    ]
    
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='grade_import_jobs'
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='grade_import_jobs'
    )
    uploaded_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='grade_imports_uploaded'
    )
    uploaded_file = models.FileField(upload_to='grade_imports/%Y/%m/%d/', null=True, blank=True)
    file_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    started_processing_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Results
    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    error_log = models.JSONField(default=list, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['academic_year', 'term', '-created_at']),
        ]
    
    def __str__(self):
        return f"Import {self.academic_year}/{self.term} - {self.status}"