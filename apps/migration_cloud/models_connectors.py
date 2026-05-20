"""Migration Cloud source-platform connector models.

Extends the existing ``MigrationBundle`` / intake / accelerator stack with
authorized source connections, discovery, staging, mapping, quarantine, and
import runs. Complements (does not replace) ``MigrationCloudAuditEvent``.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from apps.accounts.legacy_hashes.encryption import EncryptedBinaryField

User = get_user_model()


class ConnectionMethod(models.TextChoices):
    API_TOKEN = "api_token", "API token"
    OAUTH = "oauth", "OAuth"
    USERNAME_PASSWORD = "username_password", "Username and password"
    FILE_EXPORT = "file_export", "Uploaded export file"
    MANUAL_TEMPLATE = "manual_template", "Manual template"


class SourceConnectionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    VERIFYING = "verifying", "Verifying"
    VERIFIED = "verified", "Verified"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"
    REVOKED = "revoked", "Revoked"


class CredentialStorageMode(models.TextChoices):
    MEMORY_ONLY = "memory_only", "In-memory only (one-time)"
    ENCRYPTED_VAULT = "encrypted_vault", "Encrypted at rest"
    EXTERNAL_SECRET_MANAGER = "external_secret_manager", "External secret manager"


class ConnectorCertificationStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    EXPERIMENTAL = "experimental", "Experimental"
    VERIFIED_TEST = "verified_test", "Verified in test"
    PILOT_READY = "pilot_ready", "Pilot ready"
    PRODUCTION_READY = "production_ready", "Production ready"


class DiscoveryRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class StagingBatchStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    STAGED = "staged", "Staged"
    VALIDATED = "validated", "Validated"
    FAILED = "failed", "Failed"


class FieldMappingStatus(models.TextChoices):
    SUGGESTED = "suggested", "Suggested"
    CONFIRMED = "confirmed", "Confirmed"
    IGNORED = "ignored", "Ignored"
    NEEDS_REVIEW = "needs_review", "Needs review"


class QuarantineItemStatus(models.TextChoices):
    OPEN = "open", "Open"
    FIXED = "fixed", "Fixed"
    IGNORED = "ignored", "Ignored"
    BLOCKED = "blocked", "Blocked"


class ImportRunStatus(models.TextChoices):
    PREVIEW = "preview", "Preview"
    READY = "ready", "Ready"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    ROLLED_BACK = "rolled_back", "Rolled back"
    PARTIAL = "partial", "Partial"


class MigrationConnectorProfile(models.Model):
    """Vendor connector registry row (platform-wide, not tenant-scoped)."""

    key = models.SlugField(max_length=64, unique=True, db_index=True)
    display_name = models.CharField(max_length=120)
    vendor_name = models.CharField(max_length=120, blank=True)
    supported_methods = models.JSONField(default=list, blank=True)
    supports_api = models.BooleanField(default=False)
    supports_export = models.BooleanField(default=True)
    supports_browser_export = models.BooleanField(default=False)
    certification_status = models.CharField(
        max_length=32,
        choices=ConnectorCertificationStatus.choices,
        default=ConnectorCertificationStatus.PLANNED,
        db_index=True,
    )
    supported_entities = models.JSONField(default=list, blank=True)
    known_limitations = models.TextField(blank=True)
    rate_limit_notes = models.TextField(blank=True)
    auth_notes = models.TextField(blank=True)
    mapping_template = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_name",)
        verbose_name = "Migration connector profile"
        verbose_name_plural = "Migration connector profiles"

    def __str__(self) -> str:
        return self.display_name


class MigrationSourceConnection(models.Model):
    """Authorized source-platform connection for one tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_source_connections",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_source_connections_created",
    )
    connector_profile = models.ForeignKey(
        MigrationConnectorProfile,
        on_delete=models.PROTECT,
        related_name="source_connections",
    )
    source_name = models.CharField(max_length=200, blank=True)
    source_platform_type = models.CharField(max_length=64, db_index=True)
    source_url = models.URLField(max_length=500, blank=True)
    connection_method = models.CharField(
        max_length=32,
        choices=ConnectionMethod.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=SourceConnectionStatus.choices,
        default=SourceConnectionStatus.DRAFT,
        db_index=True,
    )
    credential_reference = models.CharField(
        max_length=128,
        blank=True,
        help_text="Opaque handle — never the secret itself.",
    )
    credential_storage_mode = models.CharField(
        max_length=32,
        choices=CredentialStorageMode.choices,
        default=CredentialStorageMode.MEMORY_ONLY,
    )
    credential_ciphertext = EncryptedBinaryField(
        null=True,
        blank=True,
        help_text="Fernet-wrapped credential blob when storage_mode=encrypted_vault.",
    )
    last_verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    authorization_confirmed = models.BooleanField(default=False)
    authorization_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_source_authorizations",
    )
    authorization_confirmed_at = models.DateTimeField(null=True, blank=True)
    terms_acknowledged = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    linked_bundle = models.ForeignKey(
        "migration_cloud.MigrationBundle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_connections",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("school", "status")),
            models.Index(fields=("school", "source_platform_type")),
        ]

    def __str__(self) -> str:
        return f"{self.source_platform_type} ({self.school_id})"

    def mark_verified(self) -> None:
        self.status = SourceConnectionStatus.VERIFIED
        self.last_verified_at = timezone.now()
        self.save(update_fields=["status", "last_verified_at", "updated_at"])

    def mark_failed(self) -> None:
        self.status = SourceConnectionStatus.FAILED
        self.save(update_fields=["status", "updated_at"])

    def mark_revoked(self) -> None:
        self.status = SourceConnectionStatus.REVOKED
        self.save(update_fields=["status", "updated_at"])


class MigrationDiscoveryRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_discovery_runs",
    )
    source_connection = models.ForeignKey(
        MigrationSourceConnection,
        on_delete=models.CASCADE,
        related_name="discovery_runs",
    )
    status = models.CharField(
        max_length=16,
        choices=DiscoveryRunStatus.choices,
        default=DiscoveryRunStatus.PENDING,
        db_index=True,
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_discovery_runs_started",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    discovered_entities = models.JSONField(default=list, blank=True)
    counts_by_entity = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    external_blockers = models.JSONField(default=list, blank=True)
    audit_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("school", "status"))]

    def complete(self, *, summary: dict | None = None) -> None:
        self.status = DiscoveryRunStatus.COMPLETED
        self.completed_at = timezone.now()
        if summary:
            self.audit_summary = summary
        self.save(update_fields=["status", "completed_at", "audit_summary"])


class MigrationStagingBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_staging_batches",
    )
    source_connection = models.ForeignKey(
        MigrationSourceConnection,
        on_delete=models.CASCADE,
        related_name="staging_batches",
    )
    discovery_run = models.ForeignKey(
        MigrationDiscoveryRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staging_batches",
    )
    status = models.CharField(
        max_length=16,
        choices=StagingBatchStatus.choices,
        default=StagingBatchStatus.PENDING,
        db_index=True,
    )
    entity_type = models.CharField(max_length=64, db_index=True)
    raw_count = models.PositiveIntegerField(default=0)
    valid_count = models.PositiveIntegerField(default=0)
    invalid_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    staged_payload_reference = models.CharField(max_length=256, blank=True)
    staged_rows = models.JSONField(
        default=list,
        blank=True,
        help_text="Normalized row dicts staged for bundle ingest (never credentials).",
    )
    mapping_version = models.CharField(max_length=32, blank=True, default="v1")
    data_quality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("school", "entity_type", "status"))]


class MigrationFieldMapping(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_field_mappings",
    )
    source_connection = models.ForeignKey(
        MigrationSourceConnection,
        on_delete=models.CASCADE,
        related_name="field_mappings",
    )
    source_entity = models.CharField(max_length=64, db_index=True)
    source_field = models.CharField(max_length=128)
    destination_model = models.CharField(max_length=128, blank=True)
    destination_field = models.CharField(max_length=128, blank=True)
    transform_rule = models.CharField(max_length=64, blank=True)
    required = models.BooleanField(default=False)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=16,
        choices=FieldMappingStatus.choices,
        default=FieldMappingStatus.SUGGESTED,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("source_entity", "source_field")
        unique_together = (("source_connection", "source_entity", "source_field"),)


class MigrationQuarantineItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_quarantine_items",
    )
    staging_batch = models.ForeignKey(
        MigrationStagingBatch,
        on_delete=models.CASCADE,
        related_name="quarantine_items",
    )
    entity_type = models.CharField(max_length=64, db_index=True)
    source_identifier = models.CharField(max_length=256, blank=True)
    issue_code = models.CharField(max_length=64, db_index=True)
    issue_message = models.TextField()
    raw_payload = models.JSONField(default=dict, blank=True)
    suggested_fix = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=QuarantineItemStatus.choices,
        default=QuarantineItemStatus.OPEN,
        db_index=True,
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_quarantine_resolutions",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("school", "status", "issue_code"))]


class MigrationImportRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_import_runs",
    )
    source_connection = models.ForeignKey(
        MigrationSourceConnection,
        on_delete=models.CASCADE,
        related_name="import_runs",
    )
    staging_batch = models.ForeignKey(
        MigrationStagingBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_runs",
    )
    bundle = models.ForeignKey(
        "migration_cloud.MigrationBundle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connector_import_runs",
    )
    status = models.CharField(
        max_length=16,
        choices=ImportRunStatus.choices,
        default=ImportRunStatus.PREVIEW,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_import_runs_started",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_counts = models.JSONField(default=dict, blank=True)
    updated_counts = models.JSONField(default=dict, blank=True)
    skipped_counts = models.JSONField(default=dict, blank=True)
    error_counts = models.JSONField(default=dict, blank=True)
    rollback_snapshot_reference = models.CharField(max_length=256, blank=True)
    audit_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("school", "status"))]


class MigrationAuditEvent(models.Model):
    """School-scoped connector workflow audit (queryable in wizard UI).

    Complements the tamper-evident ``MigrationCloudAuditEvent`` chain; never
    stores credentials or raw PII.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_audit_events",
    )
    event_type = models.CharField(max_length=64, db_index=True)
    source_connection = models.ForeignKey(
        MigrationSourceConnection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    discovery_run = models.ForeignKey(
        MigrationDiscoveryRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    staging_batch = models.ForeignKey(
        MigrationStagingBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    import_run = models.ForeignKey(
        MigrationImportRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("school", "event_type", "created_at"))]
