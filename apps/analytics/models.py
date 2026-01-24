# Imports
from django.db import models
from apps.academics.models import AcademicYear, Term, Classroom
from apps.accounts.validators import validate_grade_import_file, validate_file_size_5mb
# --- Phase 8: AttendanceLog stub for dashboard metrics ---


class AttendanceLog(models.Model):
    date = models.DateField()
    status = models.CharField(max_length=20)
    # Add more fields as needed for real implementation

    class Meta:
        app_label = 'analytics'

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
    uploaded_file = models.FileField(
        upload_to='grade_imports/%Y/%m/%d/',
        null=True,
        blank=True,
        validators=[validate_grade_import_file, validate_file_size_5mb],
    )
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
