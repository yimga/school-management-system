"""Universal Migration Cloud — bundle and artifact models (Phase U1).

A ``MigrationBundle`` is the *whole school's data drop*, regardless of shape.
A ``MigrationArtifact`` is one file/table/sheet inside that bundle, including
artifacts unpacked from a parent archive.

The bundle owns the lifecycle (intake → profile → classify → map → apply →
reconcile). Each apply step creates one or more child ``MigrationRun`` rows
(``apps.automation.models.MigrationRun``) and reuses the existing rollback,
quarantine, and reconciliation surfaces. Phase U1 lands the storage layer
only; later phases attach the profiler, classifier, mapper, orchestrator,
wizard, and reconciliation dashboard.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class IntakeMethod(models.TextChoices):
    """How the bundle arrived at the platform. Extended in later phases."""

    FILE_UPLOAD = "file_upload", "Direct file upload"
    ARCHIVE = "archive", "Compressed archive (zip / tar / gz / 7z)"
    URL = "url", "Remote URL / signed link"
    SFTP = "sftp", "SFTP path"
    S3 = "s3", "S3 prefix"
    SQL_DUMP = "sql_dump", "SQL dump file"
    DATABASE = "database", "Live database connection"
    OAUTH_FOLDER = "oauth_folder", "Google Drive / OneDrive / Dropbox folder (OAuth)"
    EMAIL = "email", "Email with attachments"
    API_PULL = "api_pull", "Vendor API accelerator (Phase U9)"
    PDF = "pdf", "PDF transcript stack (text + OCR fallback)"
    ACCESS_DB = "access_db", "Microsoft Access database (.mdb / .accdb)"


class BundleStatus(models.TextChoices):
    """Lifecycle of a bundle from arrival to apply."""

    PENDING = "PENDING", "Pending intake"
    INGESTING = "INGESTING", "Ingesting artifacts"
    PROFILED = "PROFILED", "Artifacts profiled"
    CLASSIFIED = "CLASSIFIED", "Source + domains classified"
    MAPPED = "MAPPED", "Fields mapped to canonical ontology"
    READY = "READY", "Ready to apply"
    APPLYING = "APPLYING", "Applying to tenant"
    APPLIED = "APPLIED", "Applied; reconciliation pending"
    RECONCILED = "RECONCILED", "Reconciliation closed"
    FAILED = "FAILED", "Failed"
    ABORTED = "ABORTED", "Aborted by operator"


class SlaTier(models.TextChoices):
    """Target SLO band, set by intake size hints (see RuntimeDefaults)."""

    SMALL = "small", "Small school (≤ 1k students, ≤ 1h)"
    MID = "mid", "Mid school (1k–10k students, ≤ 4h)"
    LARGE = "large", "Large district (10k–50k students, ≤ 12h)"
    STATE = "state", "Multi-district / state (concierge required)"


class ArtifactFormat(models.TextChoices):
    """Detected format. ``UNKNOWN`` falls back to extension-only handling."""

    CSV = "csv", "CSV"
    TSV = "tsv", "TSV"
    XLSX = "xlsx", "XLSX"
    XLS = "xls", "XLS (legacy)"
    JSON = "json", "JSON"
    JSONL = "jsonl", "JSON Lines"
    XML = "xml", "XML"
    SQL = "sql", "SQL dump"
    SQLITE = "sqlite", "SQLite database"
    PARQUET = "parquet", "Parquet"
    PDF = "pdf", "PDF (OCR — Phase U7)"
    IMAGE = "image", "Image (OCR — Phase U7)"
    ARCHIVE = "archive", "Archive (zip / tar / gz / 7z) — expanded"
    UNKNOWN = "unknown", "Unknown / extension-only"


class MigrationBundle(models.Model):
    """The whole school's data drop, regardless of shape.

    Parent of zero-or-more ``MigrationArtifact`` (one per file/table/sheet, plus
    children unpacked from archives) and parent of zero-or-more child
    ``apps.automation.models.MigrationRun`` rows that land each (domain,
    artifact) pair into the tenant during apply.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="migration_bundles",
        help_text="Target tenant. Null for pre-tenant bundles staged during signup.",
    )
    schema_name = models.CharField(
        max_length=63,
        blank=True,
        db_index=True,
        help_text="Tenant schema (django-tenants) for fan-out workers.",
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        help_text="Human-readable label for the operator (e.g. 'Sept 2026 cutover').",
    )
    intake_method = models.CharField(
        max_length=32,
        choices=IntakeMethod.choices,
        default=IntakeMethod.FILE_UPLOAD,
        db_index=True,
    )
    intake_source_uri = models.TextField(
        blank=True,
        help_text="Where it came from (path / URL / OAuth handle / API endpoint).",
    )
    source_hint = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional operator hint (e.g. 'PowerSchool export'). The "
        "classifier still runs; this is a tie-breaker, not a hard decision.",
    )
    idempotency_key = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Stable across re-runs of the same bundle; replays produce zero duplicates.",
    )
    sla_tier = models.CharField(
        max_length=16,
        choices=SlaTier.choices,
        default=SlaTier.SMALL,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=BundleStatus.choices,
        default=BundleStatus.PENDING,
        db_index=True,
    )
    size_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Bundle-wide totals: artifact_count, total_bytes, total_rows.",
    )
    discovery_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Phase U3 output: ranked source candidates + per-artifact domain guesses.",
    )
    mapping_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Phase U4 output: per-artifact column → canonical field mappings + confidences.",
    )
    reconciliation_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Phase U8 output: per-domain parity counts, sampling, scorecards.",
    )
    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_bundles_triggered",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["intake_method", "-created_at"]),
        ]
        verbose_name = "Migration bundle"
        verbose_name_plural = "Migration bundles"

    def __str__(self) -> str:
        return f"{self.label or self.idempotency_key} [{self.status}]"

    @property
    def artifact_count(self) -> int:
        return self.artifacts.count()

    def mark_status(self, new_status: str, *, summary_patch: dict | None = None) -> None:
        """Move the bundle to a new lifecycle state and patch its summary atomically."""
        self.status = new_status
        update_fields = ["status", "updated_at"]
        if summary_patch:
            self.size_summary = {**self.size_summary, **summary_patch}
            update_fields.append("size_summary")
        if new_status == BundleStatus.INGESTING and not self.started_at:
            self.started_at = timezone.now()
            update_fields.append("started_at")
        if new_status in (
            BundleStatus.RECONCILED,
            BundleStatus.FAILED,
            BundleStatus.ABORTED,
        ):
            self.completed_at = timezone.now()
            update_fields.append("completed_at")
        self.save(update_fields=update_fields)


class MigrationArtifact(models.Model):
    """A single file/table/sheet within a bundle.

    Archives (zip / tar / gz / 7z) register themselves as one artifact whose
    children are registered with ``parent_archive`` set, preserving lineage so
    re-runs and quarantine drill-downs can trace back to the original drop.
    """

    bundle = models.ForeignKey(
        MigrationBundle,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    parent_archive = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text="Set when this artifact was unpacked from a parent archive.",
    )
    path_within_bundle = models.TextField(
        help_text="Path of this artifact relative to bundle root (preserves subfolder shape).",
    )
    filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=128, blank=True, db_index=True)
    detected_format = models.CharField(
        max_length=16,
        choices=ArtifactFormat.choices,
        default=ArtifactFormat.UNKNOWN,
        db_index=True,
    )
    byte_size = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True)
    encoding = models.CharField(
        max_length=32,
        blank=True,
        help_text="Detected text encoding (utf-8, cp1252, etc.); blank for binary.",
    )
    row_count = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="For tabular formats only; null for archives / binaries / pre-profile.",
    )
    column_count = models.IntegerField(null=True, blank=True)
    locale_hints = models.JSONField(
        default=dict,
        blank=True,
        help_text="Date format, decimal separator, name order, etc. (Phase U2 fills this).",
    )
    profile = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full artifact profile (Phase U2): per-column types, samples, PII flags.",
    )
    inferred_source = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Top source-system guess from Phase U3 classifier (e.g. 'powerschool', 'unknown_custom').",
    )
    inferred_domain = models.JSONField(
        default=list,
        blank=True,
        help_text="Phase U3 ranked domain candidates: [{'domain': 'students', 'confidence': 0.93}, ...].",
    )
    quarantined = models.BooleanField(default=False, db_index=True)
    quarantine_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["bundle_id", "path_within_bundle"]
        indexes = [
            models.Index(fields=["bundle", "detected_format"]),
            models.Index(fields=["sha256"]),
            models.Index(fields=["quarantined", "bundle"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["bundle", "sha256", "path_within_bundle"],
                name="uniq_artifact_per_bundle_path",
            ),
        ]
        verbose_name = "Migration artifact"
        verbose_name_plural = "Migration artifacts"

    def __str__(self) -> str:
        return f"{self.path_within_bundle} ({self.detected_format})"
