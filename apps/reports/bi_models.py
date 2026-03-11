"""
Phase 9 Task 1: Business Intelligence & Reporting Platform
Executive dashboards, ad-hoc reports, data export, scheduled reporting

INTEGRATION NOTE: This module extends existing infrastructure:
- Uses existing DashboardWidget from apps.runtime_blueprints.models
- Extends AdminDashboardService and AdvancedAnalyticsService
- Adds ReportDefinition, ScheduledReport, MaterializedReportCache
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from apps.runtime_blueprints.models import DashboardWidget
import json

User = get_user_model()


class ReportDefinition(models.Model):
    """Defines reusable report templates"""
    
    REPORT_TYPES = [
        ('FINANCE', 'Financial Report'),
        ('ACADEMIC', 'Academic Performance'),
        ('ATTENDANCE', 'Attendance Report'),
        ('ENROLLMENT', 'Enrollment Statistics'),
        ('CUSTOM', 'Custom Query'),
    ]
    
    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    description = models.TextField(blank=True)
    query_template = models.TextField()  # SQL or Django ORM query template
    parameters = models.JSONField(default=dict)  # Expected parameters
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_reports')
    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['report_type', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.report_type})"


class ReportExecution(models.Model):
    """Track report execution history"""
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    report_definition = models.ForeignKey(ReportDefinition, on_delete=models.CASCADE)
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    parameters = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    result_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    execution_time_ms = models.IntegerField(null=True)
    row_count = models.IntegerField(null=True)
    file_path = models.CharField(max_length=500, blank=True)  # For exported files
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['executed_by', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.report_definition.name} - {self.status}"


# NOTE: DashboardWidget already exists in apps.siteconfig.models_dashboard
# We import and reuse it instead of creating a duplicate


class UserDashboard(models.Model):
    """User's personalized dashboard configuration"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    widgets = models.ManyToManyField(DashboardWidget, through='DashboardWidgetPlacement')
    layout_config = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Dashboard for {self.user.username}"


class DashboardWidgetPlacement(models.Model):
    """Position and size of widgets on dashboard"""
    
    dashboard = models.ForeignKey(UserDashboard, on_delete=models.CASCADE)
    widget = models.ForeignKey(DashboardWidget, on_delete=models.CASCADE)
    position_x = models.IntegerField(default=0)
    position_y = models.IntegerField(default=0)
    width = models.IntegerField(default=1)
    height = models.IntegerField(default=1)
    is_visible = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('dashboard', 'widget')
        ordering = ['position_y', 'position_x']


class ScheduledReport(models.Model):
    """Scheduled report generation and delivery"""
    
    FREQUENCY_CHOICES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
    ]
    
    report_definition = models.ForeignKey(ReportDefinition, on_delete=models.CASCADE)
    schedule_frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    schedule_time = models.TimeField()
    recipients = models.JSONField(default=list)  # Email addresses
    parameters = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['next_run']
    
    def __str__(self):
        return f"{self.report_definition.name} - {self.schedule_frequency}"


class MaterializedReportCache(models.Model):
    """Cache for expensive report queries"""
    
    cache_key = models.CharField(max_length=255, unique=True, db_index=True)
    report_type = models.CharField(max_length=50)
    data = models.JSONField()
    parameters = models.JSONField(default=dict)
    row_count = models.IntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['cache_key', 'expires_at']),
            models.Index(fields=['report_type', 'generated_at']),
        ]
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def __str__(self):
        return f"Cache: {self.cache_key}"


# ========== Phase 9: Ad-hoc report builder ==========


class AdHocReportDefinition(models.Model):
    """
    User-defined ad-hoc report: entity, columns, filters, date range.
    Runner builds query and returns CSV/JSON. Optional scheduling via ScheduledReport.
    """
    ENTITY_TYPES = [
        ('STUDENTS', 'Students'),
        ('ATTENDANCE', 'Attendance'),
        ('FINANCE', 'Finance (invoices/payments)'),
        ('ENROLLMENT', 'Enrollment'),
        ('CUSTOM', 'Custom'),
    ]
    OUTPUT_FORMATS = [
        ('CSV', 'CSV'),
        ('JSON', 'JSON'),
    ]

    name = models.CharField(max_length=255)
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='adhoc_report_definitions',
        null=True,
        blank=True,
        help_text='Tenant scope; null for global.',
    )
    entity_type = models.CharField(max_length=32, choices=ENTITY_TYPES, default='STUDENTS')
    columns = models.JSONField(
        default=list,
        help_text='List of column keys to output, e.g. ["id", "first_name", "last_name", "classroom__name"].',
    )
    filters = models.JSONField(
        default=dict,
        help_text='Filters: {"classroom_id": 1, "is_active": true} or {"date_from": "2024-01-01", "date_to": "2024-12-31"}.',
    )
    date_from = models.DateField(null=True, blank=True, help_text='Override or default date range start.')
    date_to = models.DateField(null=True, blank=True, help_text='Override or default date range end.')
    output_format = models.CharField(max_length=10, choices=OUTPUT_FORMATS, default='CSV')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='adhoc_report_definitions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'entity_type']),
            models.Index(fields=['school', 'is_active']),
        ]
        verbose_name = 'Ad-hoc report definition'
        verbose_name_plural = 'Ad-hoc report definitions'

    def __str__(self):
        return f"{self.name} ({self.entity_type})"


class AdHocReportExecution(models.Model):
    """Track ad-hoc report run history."""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    definition = models.ForeignKey(AdHocReportDefinition, on_delete=models.CASCADE, related_name='executions')
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    parameters_override = models.JSONField(default=dict, help_text='Optional override for date_from/date_to or filters.')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    row_count = models.IntegerField(null=True, blank=True)
    file_path = models.CharField(max_length=500, blank=True)
    error_message = models.TextField(blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['definition', 'created_at'])]

    def __str__(self):
        return f"{self.definition.name} - {self.status} @ {self.created_at}"
