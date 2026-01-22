"""
Phase 8 Task 1: Compliance Framework
Comprehensive audit, access control, and compliance models

Implements:
- Access control and RBAC
- Audit logging
- Compliance reporting
- Threat detection
- Data integrity
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import URLValidator, validate_ipv4_address
import json
from datetime import timedelta


class AccessLog(models.Model):
    """Track all user access to sensitive data"""
    
    ACCESS_TYPES = [
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('PROFILE_VIEW', 'Profile View'),
        ('GRADE_VIEW', 'Grade View'),
        ('FINANCE_VIEW', 'Finance View'),
        ('ADMIN_ACCESS', 'Admin Access'),
        ('EXPORT', 'Data Export'),
        ('IMPORT', 'Data Import'),
        ('REPORT_DOWNLOAD', 'Report Download'),
        ('API_CALL', 'API Call'),
        ('FAILED_LOGIN', 'Failed Login'),
        ('PASSWORD_CHANGE', 'Password Change'),
        ('PERMISSION_DENIED', 'Permission Denied'),
        ('DATA_ACCESS', 'Data Access'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPES)
    resource = models.CharField(max_length=255, help_text="Resource accessed (e.g., /api/grades/)")
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=[('SUCCESS', 'Success'), ('FAILURE', 'Failure'), ('PARTIAL', 'Partial')],
        default='SUCCESS'
    )
    details = models.JSONField(default=dict, blank=True)
    country = models.CharField(max_length=2, blank=True, help_text="ISO country code")
    
    class Meta:
        verbose_name = 'Access Log'
        verbose_name_plural = 'Access Logs'
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['access_type', '-timestamp']),
            models.Index(fields=['ip_address']),
        ]
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user} - {self.access_type} - {self.timestamp}"


class AuditLog(models.Model):
    """Track all data modifications for compliance"""
    
    ACTIONS = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('RESTORE', 'Restore'),
        ('EXPORT', 'Export'),
        ('IMPORT', 'Import'),
        ('BULK_UPDATE', 'Bulk Update'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTIONS)
    app_label = models.CharField(max_length=50)
    model_name = models.CharField(max_length=50)
    object_id = models.IntegerField()
    object_repr = models.TextField(max_length=500)
    changes = models.JSONField(default=dict, blank=True, help_text="Before/after comparison")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField()
    reason = models.TextField(blank=True, help_text="Reason for change")
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_audits'
    )
    
    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['action', '-timestamp']),
        ]
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.action} {self.model_name} by {self.user} at {self.timestamp}"


class ComplianceReport(models.Model):
    """Generate compliance reports for regulatory requirements"""
    
    REPORT_TYPES = [
        ('GDPR', 'GDPR Compliance'),
        ('FERPA', 'FERPA Compliance'),
        ('COPPA', 'COPPA Compliance'),
        ('DATA_RETENTION', 'Data Retention'),
        ('ACCESS_CONTROL', 'Access Control'),
        ('INCIDENT', 'Incident Report'),
        ('AUDIT_TRAIL', 'Audit Trail'),
        ('DATA_INTEGRITY', 'Data Integrity'),
    ]
    
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    period_start = models.DateField()
    period_end = models.DateField()
    summary = models.TextField()
    findings = models.JSONField(default=dict)
    recommendations = models.JSONField(default=list)
    file_path = models.FileField(upload_to='compliance_reports/', blank=True)
    
    class Meta:
        verbose_name = 'Compliance Report'
        verbose_name_plural = 'Compliance Reports'
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.report_type} - {self.generated_at.date()}"


class ThreatDetectionConfig(models.Model):
    """Configure threat detection rules"""
    
    THREAT_TYPES = [
        ('BRUTE_FORCE', 'Brute Force Attack'),
        ('DATA_EXFIL', 'Data Exfiltration'),
        ('PRIVILEGE_ESCALATION', 'Privilege Escalation'),
        ('ANOMALOUS_ACCESS', 'Anomalous Access Pattern'),
        ('RATE_LIMIT_VIOLATION', 'Rate Limit Violation'),
        ('SUSPICIOUS_EXPORT', 'Suspicious Export'),
    ]
    
    threat_type = models.CharField(max_length=25, choices=THREAT_TYPES, unique=True)
    enabled = models.BooleanField(default=True)
    threshold = models.IntegerField(help_text="Detection threshold")
    time_window = models.IntegerField(help_text="Time window in seconds")
    action = models.CharField(
        max_length=20,
        choices=[('LOG', 'Log'), ('ALERT', 'Alert'), ('BLOCK', 'Block'), ('NOTIFY', 'Notify')],
        default='ALERT'
    )
    alert_email = models.EmailField(blank=True)
    active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Threat Detection Config'
        verbose_name_plural = 'Threat Detection Configs'
    
    def __str__(self):
        return f"{self.threat_type} (Threshold: {self.threshold})"


class IPAccessRule(models.Model):
    """IP-based access control"""
    
    ip_address = models.GenericIPAddressField(unique=True)
    action = models.CharField(
        max_length=10,
        choices=[('ALLOW', 'Allow'), ('DENY', 'Deny'), ('RESTRICT', 'Restrict')],
        default='ALLOW'
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name = 'IP Access Rule'
        verbose_name_plural = 'IP Access Rules'
    
    def __str__(self):
        return f"{self.ip_address} - {self.action}"


class CountryAccessRule(models.Model):
    """Country-based access control"""
    
    country_code = models.CharField(
        max_length=2,
        unique=True,
        help_text="ISO 3166-1 alpha-2 country code"
    )
    country_name = models.CharField(max_length=100)
    action = models.CharField(
        max_length=10,
        choices=[('ALLOW', 'Allow'), ('DENY', 'Deny'), ('RESTRICT', 'Restrict')],
        default='ALLOW'
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name = 'Country Access Rule'
        verbose_name_plural = 'Country Access Rules'
    
    def __str__(self):
        return f"{self.country_name} - {self.action}"


class AlertDigest(models.Model):
    """Aggregated alerts for digest emails"""
    
    DIGEST_TYPES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
    ]
    
    recipient = models.EmailField()
    digest_type = models.CharField(max_length=10, choices=DIGEST_TYPES)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    alerts = models.JSONField(default=list)
    summary = models.TextField()
    sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Alert Digest'
        verbose_name_plural = 'Alert Digests'
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.digest_type} - {self.recipient} - {self.start_date.date()}"


class IncidentTicket(models.Model):
    """Track security incidents"""
    
    SEVERITY = [
        ('CRITICAL', 'Critical'),
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    ]
    
    STATUS = [
        ('OPEN', 'Open'),
        ('INVESTIGATING', 'Investigating'),
        ('RESOLVED', 'Resolved'),
        ('CLOSED', 'Closed'),
    ]
    
    incident_id = models.CharField(max_length=50, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY)
    status = models.CharField(max_length=15, choices=STATUS, default='OPEN')
    reported_at = models.DateTimeField(auto_now_add=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    attachments = models.JSONField(default=list)
    
    class Meta:
        verbose_name = 'Incident Ticket'
        verbose_name_plural = 'Incident Tickets'
        ordering = ['-reported_at']
    
    def __str__(self):
        return f"{self.incident_id} - {self.title}"
