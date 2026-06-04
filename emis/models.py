from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


def _emis_export_upload_to(instance, filename):
    """Tenant-scoped path for EMISExport.file_path (Section 25.3). School from academic_year."""
    ay = getattr(instance, "academic_year", None)
    school_id = getattr(ay, "school_id", None) if ay else None
    if school_id is None:
        return f"tenant_uploads/emis_exports/{filename}"
    return f"tenants/{school_id}/emis_exports/{filename}"


class EMISExport(models.Model):
    """Model to track EMIS data exports"""

    EXPORT_TYPES = [
        ('students', 'Student Data'),
        ('teachers', 'Teacher Data'),
        ('subjects', 'Subject Data'),
        ('enrollment', 'Enrollment Data'),
        ('performance', 'Academic Performance'),
        ('infrastructure', 'School Infrastructure'),
        ('full', 'Complete EMIS Dataset'),
    ]

    export_type = models.CharField(
        max_length=20,
        choices=EXPORT_TYPES,
        default='full'
    )

    academic_year = models.ForeignKey(
        'academics.AcademicYear',
        on_delete=models.CASCADE,
        related_name='emis_exports',
        # emis is in SHARED_APPS (public schema); academics is in TENANT_APPS.
        # A real cross-schema FK constraint can't be created in the public schema
        # (academics_* tables live only in tenant schemas), so disable it. Same
        # pattern as compliance.FerpaDisclosure.student / siteconfig.*.campus.
        db_constraint=False,
    )

    term = models.ForeignKey(
        'academics.Term',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='emis_exports',
        # SHARED→TENANT FK: see academic_year above.
        db_constraint=False,
    )

    exported_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='emis_exports'
    )

    export_date = models.DateTimeField(default=timezone.now)

    file_path = models.FileField(
        upload_to=_emis_export_upload_to,
        null=True,
        blank=True
    )

    record_count = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )

    error_message = models.TextField(blank=True)

    # Country-specific fields for multi-country support
    country_code = models.CharField(
        max_length=3,
        default='CMR',
        help_text='ISO 3166-1 alpha-3 country code'
    )

    ministry_format = models.CharField(
        max_length=50,
        blank=True,
        help_text='Specific ministry format requirements'
    )

    class Meta:
        ordering = ['-export_date']
        verbose_name = 'EMIS Export'
        verbose_name_plural = 'EMIS Exports'

    def __str__(self):
        return f"{self.get_export_type_display()} - {self.academic_year} ({self.export_date.date()})"


class EMISFieldMapping(models.Model):
    """Model to define field mappings for different country EMIS formats"""

    country_code = models.CharField(
        max_length=3,
        help_text='ISO 3166-1 alpha-3 country code'
    )

    export_type = models.CharField(
        max_length=20,
        choices=EMISExport.EXPORT_TYPES
    )

    field_name = models.CharField(
        max_length=100,
        help_text='Internal field name'
    )

    mapped_name = models.CharField(
        max_length=100,
        help_text='EMIS export field name'
    )

    data_type = models.CharField(
        max_length=20,
        choices=[
            ('string', 'String'),
            ('integer', 'Integer'),
            ('decimal', 'Decimal'),
            ('date', 'Date'),
            ('boolean', 'Boolean'),
        ],
        default='string'
    )

    required = models.BooleanField(default=False)

    description = models.TextField(blank=True)

    class Meta:
        unique_together = ['country_code', 'export_type', 'field_name']
        verbose_name = 'EMIS Field Mapping'
        verbose_name_plural = 'EMIS Field Mappings'

    def __str__(self):
        return f"{self.country_code} - {self.export_type}: {self.field_name} -> {self.mapped_name}"


class EMISCompliance(models.Model):
    """Model to track EMIS compliance requirements by country"""

    country_code = models.CharField(
        max_length=3,
        unique=True,
        help_text='ISO 3166-1 alpha-3 country code'
    )

    country_name = models.CharField(max_length=100)

    ministry_name = models.CharField(
        max_length=200,
        help_text='Name of education ministry'
    )

    emis_version = models.CharField(
        max_length=20,
        help_text='EMIS format version/standard'
    )

    last_updated = models.DateTimeField(auto_now=True)

    requirements_url = models.URLField(
        blank=True,
        help_text='URL to official EMIS requirements'
    )

    notes = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'EMIS Compliance'
        verbose_name_plural = 'EMIS Compliances'

    def __str__(self):
        return f"{self.country_name} ({self.country_code}) - {self.emis_version}"
