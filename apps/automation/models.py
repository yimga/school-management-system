"""
Automation models for tracking execution and approvals.
"""

import logging
from django.db import DatabaseError, IntegrityError, models
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context

User = get_user_model()
logger = logging.getLogger(__name__)


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
    execution_type = models.CharField(
        max_length=20, choices=ExecutionType.choices, default=ExecutionType.SCHEDULED
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
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

    def mark_completed(
        self,
        status: str,
        records_processed: int = 0,
        records_failed: int = 0,
        error_message: str = "",
        summary: dict = None,
    ):
        """Mark execution as completed."""
        self.status = status
        self.completed_at = timezone.now()
        self.records_processed = records_processed
        self.records_failed = records_failed
        self.error_message = error_message
        if summary:
            self.execution_summary = summary
        self.save(
            update_fields=[
                "status",
                "completed_at",
                "records_processed",
                "records_failed",
                "error_message",
                "execution_summary",
            ]
        )


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
    execution_summary = models.JSONField(
        default=dict, help_text="Summary of what will be executed"
    )
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
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
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
        self.save(
            update_fields=["status", "approved_by", "approved_at", "rejection_reason"]
        )


class MigrationRun(models.Model):
    """
    Audit record for data migration runs (Phase 5 migration cloud).
    Tracks upload → mapping → dry-run or run with scorecard (row_count, created, updated, errors).
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        PARTIAL = "PARTIAL", "Partial"
        FAILED = "FAILED", "Failed"

    class ExceptionAck(models.TextChoices):
        """Operator exception queue: runs with errors need review until closed."""
        NA = "NA", "N/A"
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="migration_runs",
    )
    migration_type = models.CharField(
        max_length=64, db_index=True
    )  # e.g. "students", "grades"
    dry_run = models.BooleanField(default=False, db_index=True)
    row_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_runs",
    )
    execution_summary = models.JSONField(
        default=dict, blank=True
    )  # scorecard details, error snippets
    error_message = models.TextField(blank=True)
    # Section 11.1: read-only legacy view — uploaded rows snapshot (no PII in logs)
    legacy_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Read-only copy of uploaded rows for legacy view (no PII in logs).",
    )
    # Rollback (11.1, 29.6): store enough to revert last run; optional created_ids, updated_ids_with_old_values per migration_type
    rollback_snapshot = models.JSONField(default=dict, blank=True)
    rolled_back_by_run = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rollback_of_run",
        help_text="When set, this run reverted the migration recorded by the linked run.",
    )
    exception_ack_status = models.CharField(
        max_length=16,
        choices=ExceptionAck.choices,
        default=ExceptionAck.NA,
        db_index=True,
    )
    exception_ack_at = models.DateTimeField(null=True, blank=True)
    exception_ack_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_exception_acks",
    )
    exception_ack_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["migration_type", "-started_at"]),
            models.Index(fields=["school", "-started_at"]),
            models.Index(fields=["exception_ack_status", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.migration_type} ({'dry-run' if self.dry_run else 'run'}) - {self.status} ({self.started_at})"

    def mark_completed(
        self,
        status: str,
        created_count: int = 0,
        updated_count: int = 0,
        error_count: int = 0,
        error_message: str = "",
        summary: dict = None,
    ):
        self.status = status
        self.completed_at = timezone.now()
        self.created_count = created_count
        self.updated_count = updated_count
        self.error_count = error_count
        self.error_message = error_message or self.error_message
        if summary is not None:
            self.execution_summary = summary
        self.save(
            update_fields=[
                "status",
                "completed_at",
                "created_count",
                "updated_count",
                "error_count",
                "error_message",
                "execution_summary",
            ]
        )

    @property
    def can_rollback(self):
        """True if this run can be rolled back: success/partial, has snapshot, not already rolled back."""
        if self.dry_run or self.migration_type == "rollback":
            return False
        if self.rolled_back_by_run_id is not None:
            return False
        if self.status not in (self.Status.SUCCESS, self.Status.PARTIAL):
            return False
        return bool(self.rollback_snapshot)

    def trigger_rollback(self, user=None):
        """
        Create a rollback run and execute rollback handler for this migration_type.
        Rollback handler may use rollback_snapshot (e.g. created_ids, updated_ids_with_old_values).
        Returns the new MigrationRun (type=rollback) and a dict with success, message, reverted_count.
        """
        if not self.can_rollback:
            return None, {
                "success": False,
                "message": "Run cannot be rolled back (dry-run, already rolled back, or no snapshot).",
            }
        from apps.automation.rollback_handlers import run_rollback

        rollback_run = MigrationRun.objects.create(
            school=self.school,
            migration_type="rollback",
            dry_run=False,
            row_count=0,
            status=MigrationRun.Status.PENDING,
            triggered_by=user,
            execution_summary={
                "reverts_run_id": self.pk,
                "migration_type": self.migration_type,
            },
        )
        try:
            result = run_rollback(self, rollback_run)
        except (
            DatabaseError,
            IntegrityError,
            ValidationError,
            ValueError,
            TypeError,
        ) as e:
            school_id = (
                str(self.school_id) if getattr(self, "school_id", None) else None
            )
            log_exception_with_context(
                "automation.models: rollback run failed",
                school_id=school_id,
                extra={"migration_run_id": self.pk, "error": str(e)},
            )
            logger.exception("Rollback run failed for MigrationRun pk=%s", self.pk)
            result = {"success": False, "message": str(e), "reverted_count": 0}
            rollback_run.mark_completed(
                status=MigrationRun.Status.FAILED,
                error_message=str(e),
                summary={**rollback_run.execution_summary, "error": str(e)},
            )
            return rollback_run, result
        if not result.get("success") and "reverted_count" not in result:
            result["reverted_count"] = 0
        if result.get("success"):
            self.rolled_back_by_run = rollback_run
            self.save(update_fields=["rolled_back_by_run"])
            rollback_run.mark_completed(
                status=MigrationRun.Status.SUCCESS,
                created_count=0,
                updated_count=result.get("reverted_count", 0),
                error_count=0,
                summary={**rollback_run.execution_summary, **result},
            )
        else:
            rollback_run.mark_completed(
                status=MigrationRun.Status.FAILED,
                error_message=result.get("message", "Rollback failed."),
                summary={**rollback_run.execution_summary, **result},
            )
        return rollback_run, result


class MigrationProfile(models.Model):
    """
    Platform-level registry of migration connector profiles (Phase 5 migration cloud).
    Schools use these to run imports (CSV/XLSX, student/finance/attendance/grades, generic SIS).
    Seeded by seed_migration_profiles; migration_type in MigrationRun can match slug.
    """

    class Format(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "XLSX"
        GENERIC_SIS = "generic_sis", "Generic SIS"

    class Domain(models.TextChoices):
        STUDENTS = "students", "Student import"
        FINANCE = "finance", "Finance import"
        ATTENDANCE = "attendance", "Attendance import"
        GRADES = "grades", "Grades import"
        GENERIC_SIS = "generic_sis", "Generic SIS"

    class SourceSystem(models.TextChoices):
        POWERSCHOOL = "powerschool", "PowerSchool"
        BLACKBAUD = "blackbaud", "Blackbaud"
        VERACROSS = "veracross", "Veracross"
        INFINITE_CAMPUS = "infinite_campus", "Infinite Campus"
        FACTS = "facts", "FACTS"
        SKYWARD = "skyward", "Skyward"
        ALMA = "alma", "Alma"
        SQL_DUMP = "sql_dump", "SQL export"
        API_SIS = "api_sis", "API SIS"
        OTHER = "other", "Other"

    class ProfileCategory(models.TextChoices):
        VENDOR = "vendor", "Vendor"
        INSTITUTION_TYPE = "institution_type", "Institution type"
        GEOGRAPHY = "geography", "Geography"
        DATA_CONDITION = "data_condition", "Data condition"
        STRATEGY = "strategy", "Strategy"

    slug = models.SlugField(max_length=64, unique=True, db_index=True)
    source_system = models.CharField(
        max_length=32,
        choices=SourceSystem.choices,
        null=True,
        blank=True,
        db_index=True,
        help_text="Prebuilt adapter for this SIS; null/other = generic.",
    )
    profile_category = models.CharField(
        max_length=32,
        choices=ProfileCategory.choices,
        null=True,
        blank=True,
        db_index=True,
        help_text="Category for registry filtering: vendor, institution_type, geography, data_condition, strategy.",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    format = models.CharField(max_length=20, choices=Format.choices, default=Format.CSV)
    domain = models.CharField(
        max_length=32, choices=Domain.choices, default=Domain.STUDENTS
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Target fields, required columns, mapping hints for the migration wizard.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "slug"]
        verbose_name = "Migration profile"
        verbose_name_plural = "Migration profiles"

    def __str__(self):
        return f"{self.name} ({self.slug})"


class MigrationPlaybook(models.Model):
    """
    Reusable playbook: ordered list of migration profile slugs run in sequence.
    A MigrationRun can reference a playbook (or single profile); executor runs profiles in order.
    """

    slug = models.SlugField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    profile_slugs = models.JSONField(
        default=list,
        help_text="Ordered list of MigrationProfile slugs to run in sequence.",
    )
    validation_repair_defaults = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional defaults for validation/repair (e.g. strict_required, auto_remap).",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "slug"]
        verbose_name = "Migration playbook"
        verbose_name_plural = "Migration playbooks"

    def __str__(self):
        return f"{self.name} ({self.slug})"

    def get_profiles(self):
        """Resolve profile_slugs to MigrationProfile instances in order."""
        if not self.profile_slugs:
            return []
        by_slug = {
            p.slug: p
            for p in MigrationProfile.objects.filter(
                slug__in=self.profile_slugs, is_active=True
            )
        }
        return [by_slug[s] for s in self.profile_slugs if s in by_slug]


class MigrationQuarantineRecord(models.Model):
    """
    Repair and quarantine engine: records that failed validation or need repair.
    Guided repair can update resolution_payload and set status to REPAIRED, then replay.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        REPAIRED = "REPAIRED", "Repaired"
        FAILED = "FAILED", "Failed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="migration_quarantine_records",
    )
    migration_run = models.ForeignKey(
        MigrationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quarantine_records",
    )
    domain = models.CharField(max_length=32, db_index=True)  # students, grades, etc.
    row_index = models.PositiveIntegerField(help_text="1-based row index in source.")
    payload = models.JSONField(
        default=dict, blank=True, help_text="Row data (sanitized)."
    )
    issue_class = models.CharField(
        max_length=64, db_index=True
    )  # duplicate, missing_required, invalid_ref
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_payload = models.JSONField(
        default=dict, blank=True, help_text="Repaired row or resolution note."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "domain", "status"]),
        ]
        verbose_name = "Migration quarantine record"
        verbose_name_plural = "Migration quarantine records"

    def __str__(self):
        return f"Quarantine {self.domain} row {self.row_index} ({self.issue_class})"
