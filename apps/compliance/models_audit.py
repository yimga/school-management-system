"""
Audit & Monitoring models for comprehensive logging, access control, and compliance tracking.
Phase 4: Audit logging for all model changes, user actions, and system events.
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.conf import settings
import json


class AuditLog(models.Model):
    """
    Comprehensive audit trail capturing all significant system actions:
    - Model create/update/delete
    - Sensitive data access (invoices, grades, personal info)
    - Admin actions
    - Authentication events
    - Permission changes
    """

    class Action(models.TextChoices):
        CREATE = "CREATE", "Record Created"
        UPDATE = "UPDATE", "Record Updated"
        DELETE = "DELETE", "Record Deleted"
        VIEW = "VIEW", "Record Viewed"
        EXPORT = "EXPORT", "Data Exported"
        LOGIN = "LOGIN", "User Login"
        LOGOUT = "LOGOUT", "User Logout"
        PERMISSION_GRANT = "PERM_GRANT", "Permission Granted"
        PERMISSION_REVOKE = "PERM_REVOKE", "Permission Revoked"
        PUBLISH = "PUBLISH", "Content Published"
        APPROVE = "APPROVE", "Action Approved"
        REJECT = "REJECT", "Action Rejected"
        ACCESS_DENIED = "ACCESS_DENIED", "Access Denied"

    class Sensitivity(models.TextChoices):
        LOW = "LOW", "Public"
        MEDIUM = "MEDIUM", "Restricted"
        HIGH = "HIGH", "Confidential"
        CRITICAL = "CRITICAL", "Critical"

    # Actor & context
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
        help_text="User who performed the action (null if system-initiated)"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    # Action details
    action = models.CharField(max_length=20, choices=Action.choices)
    model_name = models.CharField(max_length=100, help_text="e.g., 'Invoice', 'Evaluation'")
    object_id = models.CharField(max_length=200, help_text="Primary key of affected object")
    object_repr = models.CharField(max_length=500, blank=True, help_text="String representation of object")

    # Data & sensitivity
    sensitivity = models.CharField(
        max_length=20,
        choices=Sensitivity.choices,
        default=Sensitivity.MEDIUM,
        help_text="Data sensitivity classification"
    )
    old_values = models.JSONField(null=True, blank=True, help_text="Pre-change state (for UPDATE/DELETE)")
    new_values = models.JSONField(null=True, blank=True, help_text="Post-change state (for CREATE/UPDATE)")
    changed_fields = models.JSONField(
        null=True,
        blank=True,
        help_text="List of field names that changed"
    )

    # Context & metadata
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    app_label = models.CharField(max_length=100, db_index=True)
    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reason/comment for the action (e.g., 'Bulk import', 'Correction')"
    )
    related_audit_logs = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="related_to",
        help_text="Reference to related audit entries"
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["model_name", "object_id"]),
            models.Index(fields=["action", "-timestamp"]),
            models.Index(fields=["sensitivity", "-timestamp"]),
        ]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        return f"{self.get_action_display()} {self.model_name}({self.object_id}) by {self.user or 'System'} @ {self.timestamp.isoformat()}"

    @property
    def summary(self) -> str:
        """Human-readable one-liner."""
        user_str = f"{self.user.get_full_name() or self.user.username}" if self.user else "System"
        return f"{self.get_action_display()} {self.model_name} '{self.object_repr}' by {user_str}"

    def get_changes(self) -> dict:
        """Return a dict mapping field -> (old_value, new_value) for UPDATE actions."""
        if self.action != self.Action.UPDATE or not self.changed_fields:
            return {}
        changes = {}
        for field in self.changed_fields:
            old = self.old_values.get(field) if self.old_values else None
            new = self.new_values.get(field) if self.new_values else None
            changes[field] = (old, new)
        return changes


class UserActivitySession(models.Model):
    """
    Track user sessions: login/logout, inactivity timeouts, concurrent logins.
    Helps detect suspicious access patterns.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_sessions"
    )
    session_key = models.CharField(max_length=100, unique=True)
    login_timestamp = models.DateTimeField(auto_now_add=True)
    logout_timestamp = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=500, blank=True)

    # Activity metrics
    page_views = models.PositiveIntegerField(default=0)
    api_calls = models.PositiveIntegerField(default=0)
    last_activity = models.DateTimeField(null=True, blank=True)

    # Security
    is_suspicious = models.BooleanField(default=False, help_text="Flag if unusual activity detected")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-login_timestamp"]
        indexes = [
            models.Index(fields=["user", "-login_timestamp"]),
            models.Index(fields=["is_suspicious"]),
        ]

    def __str__(self):
        status = "Active" if not self.logout_timestamp else "Logged out"
        return f"{self.user} {status} from {self.ip_address}"

    @property
    def duration_seconds(self) -> int | None:
        if self.logout_timestamp:
            return int((self.logout_timestamp - self.login_timestamp).total_seconds())
        return None


class AccessLog(models.Model):
    """
    Track access to sensitive views/APIs:
    - Who accessed what
    - When
    - From where
    - Success/failure
    """

    class AccessType(models.TextChoices):
        WEB = "WEB", "Web Page"
        API = "API", "API Call"
        DOWNLOAD = "DOWNLOAD", "File Download"
        ADMIN = "ADMIN", "Admin Interface"
        REPORT = "REPORT", "Report Generation"

    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        FORBIDDEN = "FORBIDDEN", "Access Denied"
        NOT_FOUND = "NOT_FOUND", "Not Found"
        ERROR = "ERROR", "Error"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="access_logs"
    )
    access_type = models.CharField(max_length=20, choices=AccessType.choices)
    resource = models.CharField(max_length=500, help_text="URL path or API endpoint")
    status = models.CharField(max_length=20, choices=Status.choices)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_method = models.CharField(max_length=10, blank=True)  # GET, POST, etc.
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, help_text="If status != SUCCESS")

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["resource", "-timestamp"]),
            models.Index(fields=["status", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.get_access_type_display()} {self.resource} → {self.get_status_display()} by {self.user}"


class ComplianceReport(models.Model):
    """
    Pre-computed or on-demand compliance reports for audit trails, data access, anomalies.
    """

    class ReportType(models.TextChoices):
        AUDIT_TRAIL = "AUDIT_TRAIL", "Audit Trail"
        DATA_ACCESS = "DATA_ACCESS", "Data Access Report"
        PERMISSION_SUMMARY = "PERM_SUMMARY", "Permission Summary"
        INTEGRITY_CHECK = "INTEGRITY", "Data Integrity Check"
        ANOMALY_DETECTION = "ANOMALY", "Anomaly Detection"

    report_type = models.CharField(max_length=50, choices=ReportType.choices)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="compliance_reports_generated"
    )
    start_date = models.DateField(help_text="Report period start")
    end_date = models.DateField(help_text="Report period end")

    # Results
    summary = models.JSONField(help_text="High-level metrics and findings")
    details = models.JSONField(help_text="Detailed findings, grouped by category")
    issues = models.JSONField(
        default=list,
        help_text="List of detected issues/anomalies"
    )
    export_formats = models.JSONField(
        default=list,
        help_text="Available export formats: ['pdf', 'csv', 'json']"
    )

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["report_type", "-generated_at"]),
            models.Index(fields=["start_date", "end_date"]),
        ]

    def __str__(self):
        return f"{self.get_report_type_display()} ({self.start_date} to {self.end_date}) @ {self.generated_at.isoformat()}"


class ThreatDetectionConfig(models.Model):
    """
    Persistent threat detection configuration (mute windows, thresholds).
    Overrides environment variables when present.
    """

    # Singleton pattern - only one active config
    is_active = models.BooleanField(default=True, unique=True, help_text="Only one config can be active")

    # Thresholds
    window_minutes = models.PositiveIntegerField(default=60, help_text="Lookback window in minutes")
    failed_per_user = models.PositiveIntegerField(default=10, help_text="Failed logins per user before alert")
    failed_per_ip = models.PositiveIntegerField(default=20, help_text="Failed attempts per IP before alert")
    after_hours_start = models.PositiveIntegerField(
        default=22,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="After-hours start (hour, 24h format)"
    )
    after_hours_end = models.PositiveIntegerField(
        default=6,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="After-hours end (hour, 24h format)"
    )
    after_hours_threshold = models.PositiveIntegerField(default=5, help_text="Accesses during after-hours before alert")

    # Mute window (persisted, survives restarts)
    mute_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Suppress alerts until this time (leave empty to disable mute)"
    )

    # Metadata
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="threat_config_updates"
    )

    class Meta:
        verbose_name = "Threat Detection Configuration"
        verbose_name_plural = "Threat Detection Configuration"

    def __str__(self):
        mute_status = f"(muted until {self.mute_until.isoformat()})" if self.mute_until else ""
        return f"Threat Detection Config {mute_status}"

    def is_muted(self) -> bool:
        """Check if alerts are currently muted."""
        if not self.mute_until:
            return False
        return timezone.now() < self.mute_until

    @classmethod
    def get_active(cls):
        """Get or create the active configuration."""
        config, _ = cls.objects.get_or_create(is_active=True)
        return config


class IPAccessRule(models.Model):
    """
    IP address allow/deny list for access control.
    Supports CIDR notation for IP ranges.
    """

    class RuleType(models.TextChoices):
        ALLOW = "ALLOW", "Allow (Whitelist)"
        DENY = "DENY", "Deny (Blacklist)"

    rule_type = models.CharField(max_length=10, choices=RuleType.choices)
    ip_address = models.CharField(
        max_length=100,
        help_text="IP address or CIDR range (e.g., 192.168.1.0/24)"
    )
    description = models.CharField(max_length=255, blank=True, help_text="Reason for this rule")
    is_active = models.BooleanField(default=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ip_rules_created"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Auto-disable rule after this time (optional)"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["rule_type", "is_active"]),
        ]
        verbose_name = "IP Access Rule"
        verbose_name_plural = "IP Access Rules"

    def __str__(self):
        status = "✓" if self.is_active else "✗"
        return f"{status} {self.get_rule_type_display()}: {self.ip_address}"

    def is_expired(self) -> bool:
        """Check if rule has expired."""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at

    def matches(self, ip_address: str) -> bool:
        """Check if given IP matches this rule (supports CIDR)."""
        import ipaddress
        try:
            if "/" in self.ip_address:
                # CIDR notation
                network = ipaddress.ip_network(self.ip_address, strict=False)
                return ipaddress.ip_address(ip_address) in network
            else:
                # Exact match
                return self.ip_address == ip_address
        except (ValueError, TypeError):
            return False


class CountryAccessRule(models.Model):
    """
    Country-based access control using ISO 3166-1 alpha-2 codes.
    Requires GeoIP2 or similar service for IP-to-country mapping.
    """

    class RuleType(models.TextChoices):
        ALLOW = "ALLOW", "Allow (Whitelist)"
        DENY = "DENY", "Deny (Blacklist)"

    rule_type = models.CharField(max_length=10, choices=RuleType.choices)
    country_code = models.CharField(
        max_length=2,
        help_text="ISO 3166-1 alpha-2 code (e.g., CM, NG, US)"
    )
    country_name = models.CharField(max_length=100, blank=True, help_text="Human-readable name")
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="country_rules_created"
    )

    class Meta:
        ordering = ["country_code"]
        indexes = [
            models.Index(fields=["rule_type", "is_active"]),
        ]
        verbose_name = "Country Access Rule"
        verbose_name_plural = "Country Access Rules"

    def __str__(self):
        status = "✓" if self.is_active else "✗"
        name = self.country_name or self.country_code
        return f"{status} {self.get_rule_type_display()}: {name} ({self.country_code})"
