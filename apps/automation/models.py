"""
Automation models for tracking execution and approvals.
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class AutomationExecutionLog(models.Model):
    """Track automation task execution history."""
    
    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        PARTIAL = "PARTIAL", "Partial"
        PENDING = "PENDING", "Pending"
    
    class ExecutionType(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        MANUAL = "MANUAL", "Manual"
        DRY_RUN = "DRY_RUN", "Dry Run"
    
    task_name = models.CharField(max_length=200, db_index=True)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="automation_execution_logs",
    )
    schema_name = models.CharField(max_length=63, blank=True, db_index=True)
    execution_type = models.CharField(max_length=20, choices=ExecutionType.choices, default=ExecutionType.SCHEDULED)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    records_processed = models.PositiveIntegerField(default=0)
    records_failed = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    execution_summary = models.JSONField(default=dict, blank=True)
    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="automation_executions",
    )
    
    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["task_name", "-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]
    
    def __str__(self):
        return f"{self.task_name} - {self.status} ({self.started_at})"
    
    def mark_completed(self, status: str, records_processed: int = 0, records_failed: int = 0, error_message: str = "", summary: dict = None):
        """Mark execution as completed."""
        self.status = status
        self.completed_at = timezone.now()
        self.records_processed = records_processed
        self.records_failed = records_failed
        self.error_message = error_message
        if summary:
            self.execution_summary = summary
        self.save(update_fields=["status", "completed_at", "records_processed", "records_failed", "error_message", "execution_summary"])


class AutomationApprovalQueue(models.Model):
    """Queue for automation tasks that require approval before execution."""
    
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        EXECUTED = "EXECUTED", "Executed"
    
    automation_type = models.CharField(max_length=100, db_index=True)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="automation_approval_queue",
    )
    schema_name = models.CharField(max_length=63, blank=True, db_index=True)
    execution_summary = models.JSONField(default=dict, help_text="Summary of what will be executed")
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_automations",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_automations",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    execution_log = models.ForeignKey(
        AutomationExecutionLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_queue_entries",
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["automation_type", "status"]),
        ]
    
    def __str__(self):
        return f"{self.automation_type} - {self.status} ({self.created_at})"
    
    def approve(self, approved_by: User):
        """Approve this automation request."""
        self.status = self.Status.APPROVED
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at"])
    
    def reject(self, rejected_by: User, reason: str = ""):
        """Reject this automation request."""
        self.status = self.Status.REJECTED
        self.approved_by = rejected_by
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "approved_by", "approved_at", "rejection_reason"])
