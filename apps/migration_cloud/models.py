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

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from apps.platform_runtime.append_only import AppendOnlyManager, AppendOnlyModelMixin

# v3.32.0 — encrypted-at-rest BinaryField for the webhook subscription
# secret_ciphertext column. Shares the Fernet key with the User-model
# legacy_* columns so a single key rotation covers both surfaces — see
# docs/SECURITY_KEYS.md.
#
# v3.33.0 — same Fernet shim now also wraps
# ``MigrationCloudCompanionKeypair.private_key_encrypted`` (was raw
# BinaryField in v3.32, promoted via migration 0011).
from apps.accounts.legacy_hashes.encryption import (
    EncryptedBinaryField as _EncryptedBinaryField,
)
from apps.accounts.legacy_hashes.encryption import (
    EncryptedJSONField as _EncryptedJSONField,
)
from apps.accounts.legacy_hashes.encryption import (
    encrypt_binaryfield as _webhook_encrypt_binaryfield,
)

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
    # Connector credentials (API bearer token, OAuth access token, ...) captured
    # when an operator attaches a live source to a pending bundle. Fernet-encrypted
    # at rest via the shared EncryptedJSONField (same key/rotation as the webhook
    # secret + companion keypair). NEVER logged, NEVER surfaced in a response.
    # Empty {} round-trips as the literal "{}" so unattached bundles cost nothing.
    connector_secret = _EncryptedJSONField(
        default=dict,
        blank=True,
        help_text="Encrypted-at-rest connector credentials for live-source intake "
        "(API token / OAuth access token). Reconstructed into the adapter handle "
        "at ingest; never logged or returned.",
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
    expected_totals = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Operator-supplied financial control totals enforced before APPLIED. "
            "Shape: {'finance.invoice_total_amount': '125000.00', 'students.count': 1240}. "
            "Mismatch aborts the apply with a FinancialMismatchError."
        ),
    )
    progress_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Live per-stage progress for the DAG view: "
            "{'stages': [{'name': 'INGESTING', 'pct': 100, 'rows': 1240, 'started': ..., "
            "'finished': ...}, ...], 'updated_at': iso}."
        ),
    )
    diff_mode = models.CharField(
        max_length=16,
        choices=[
            ("full", "Full re-ingest (default)"),
            ("since", "Diff mode: only rows changed since last successful bundle"),
        ],
        default="full",
        help_text="Diff-mode re-ingest: 'since' uses last_successful_apply_at to skip unchanged rows.",
    )
    diff_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When diff_mode='since', source rows older than this timestamp are skipped.",
    )
    apply_atomic = models.BooleanField(
        default=False,
        help_text=(
            "All-or-nothing apply opt-in. When True, the orchestrator wraps the whole apply "
            "in a single transaction so any quarantine-bearing artifact rolls back the bundle."
        ),
    )
    parity_drift_rollback_pct = models.FloatField(
        default=0.0,
        help_text=(
            "Auto-rollback threshold. When > 0, reconciliation that yields overall parity below "
            "this percentage triggers an automatic rollback of the apply's MigrationRun rows."
        ),
    )
    sandbox_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sandbox_clones",
        help_text="When set, this bundle is a sandbox copy of another bundle, isolated under a throwaway schema.",
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
    assigned_domain = models.CharField(
        max_length=40,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "Operator-assigned canonical domain for this file (e.g. 'students', "
            "'staff', 'finance'). Set from the multi-file upload tagger; OVERRIDES "
            "inference and accelerator routing so the operator's explicit "
            "'this file is X' always wins. Blank = auto-detect."
        ),
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


class MigrationArtifactBlob(models.Model):
    """Encrypted-at-rest copy of one artifact's source bytes (Phase U5 content store).

    Captured at ingest (Phase U1) while the intake adapter's ``content_opener``
    is still valid, then read back by the profiler (U2) and the apply
    orchestrator (U5). Before this store, only the single top-level local file at
    ``bundle.intake_source_uri`` had readable bytes downstream — **archive members
    and multi-file / remote / OAuth-folder pulls** profiled schema-only and applied
    zero rows silently. With the blob present those artifacts resolve.

    These bytes ARE student PII (rosters, grades, guardian contacts, health /
    behaviour records). Invariants:

    * **Encrypted at rest** via the shared Fernet shim (same key + rotation as
      ``MigrationBundle.connector_secret``, the webhook secret, and the companion
      keypair — see ``docs/SECURITY_KEYS.md``). The DB column is a plain BLOB /
      bytea; only the read/write value transform differs.
    * **Retention-bounded.** ``expires_at`` drives a daily purge sweep, and a
      bundle's blobs are dropped the moment it reaches ``RECONCILED`` (the source
      is no longer needed). Artifact METADATA is always retained for the audit
      trail — only the raw bytes go.
    * **Size-bounded.** Only artifacts at or under
      ``MIGRATION_CLOUD_ARTIFACT_BLOB_MAX_INLINE_BYTES`` are stored inline; larger
      artifacts are skipped (logged, never with PII) pending a file-backed Phase 2.
    * **Tenant-isolated + never logged.** Reachable only via
      ``artifact → bundle → school``, so a cross-tenant read is impossible.
    """

    artifact = models.OneToOneField(
        MigrationArtifact,
        on_delete=models.CASCADE,
        related_name="blob",
        help_text="The artifact whose raw source bytes this blob holds.",
    )
    payload = _EncryptedBinaryField(
        help_text="Fernet-encrypted source bytes. Decrypts transparently on read; never logged.",
    )
    byte_size = models.BigIntegerField(
        default=0,
        help_text="Plaintext byte length (pre-encryption); integrity + metrics only.",
    )
    sha256 = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 of the plaintext bytes; re-verified on every read.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        db_index=True,
        help_text="PII-minimisation clock; the daily purge sweep deletes blobs past this.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["expires_at"], name="mc_artifact_blob_exp_idx"),
        ]
        verbose_name = "Migration artifact blob"
        verbose_name_plural = "Migration artifact blobs"

    def __str__(self) -> str:
        return f"blob for artifact {self.artifact_id} ({self.byte_size} bytes)"


class MigrationIdMapping(models.Model):
    """Audit table mapping legacy source IDs to canonical tenant rows.

    Recorded by every lander upsert so months later an operator can answer
    "what's the new ID for old ID X?" without grepping landers or replaying
    the bundle. Tenant-scoped by ``school_id`` so the cross-tenant query
    is impossible.
    """

    bundle = models.ForeignKey(
        MigrationBundle,
        on_delete=models.CASCADE,
        related_name="id_mappings",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="migration_id_mappings",
    )
    legacy_namespace = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Source-system namespace (e.g. 'powerschool', 'blackbaud', 'unknown_custom').",
    )
    legacy_id = models.CharField(
        max_length=128,
        db_index=True,
        help_text="The original external_id / source-system row identifier.",
    )
    canonical_model = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Dotted path of the canonical model the row landed in (e.g. 'apps.people.StudentProfile').",
    )
    canonical_pk = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Primary key of the canonical row (stringified for cross-type tolerance).",
    )
    domain = models.CharField(max_length=32, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["legacy_namespace", "legacy_id"]),
            models.Index(fields=["canonical_model", "canonical_pk"]),
            models.Index(fields=["bundle", "domain"]),
        ]
        constraints = [
            # ``domain`` is part of the mapping's identity: the SAME legacy id
            # can land the SAME canonical row from two domains (a students
            # upsert then an enrollment update). Without it, the second
            # lander's update_or_create matched the first row and silently
            # rewrote its domain — the students audit entry vanished on every
            # multi-domain bundle.
            models.UniqueConstraint(
                fields=[
                    "legacy_namespace",
                    "legacy_id",
                    "canonical_model",
                    "school",
                    "domain",
                ],
                name="uniq_id_mapping_per_school_namespace",
            ),
        ]
        verbose_name = "Migration ID mapping"
        verbose_name_plural = "Migration ID mappings"

    def __str__(self) -> str:
        return f"{self.legacy_namespace}:{self.legacy_id} → {self.canonical_model}#{self.canonical_pk}"


class AssetStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    FETCHING = "FETCHING", "Fetching from source"
    STORED = "STORED", "Stored"
    FAILED = "FAILED", "Failed"


class MigrationAsset(models.Model):
    """One binary asset (student photo, immunization scan, report-card PDF, …).

    Created by the asset pipeline worker when an artifact row references an
    external file URL. Files land under
    ``MEDIA_ROOT/migration_cloud/assets/<tenant>/<entity>/<external_id>.<ext>``
    keyed by the canonical entity the asset belongs to.
    """

    bundle = models.ForeignKey(
        MigrationBundle,
        on_delete=models.CASCADE,
        related_name="assets",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="migration_assets",
    )
    entity_kind = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Canonical entity the asset belongs to (e.g. 'student', 'guardian', 'invoice').",
    )
    legacy_id = models.CharField(
        max_length=128,
        db_index=True,
        help_text="external_id of the row this asset belongs to.",
    )
    asset_kind = models.CharField(
        max_length=32,
        db_index=True,
        help_text="Discriminator (e.g. 'photo', 'immunization', 'report_card', 'transcript').",
    )
    source_uri = models.TextField(
        blank=True,
        help_text="Where the asset was fetched from (http(s):// / s3:// / file:// / data:base64).",
    )
    stored_path = models.TextField(
        blank=True,
        help_text="MEDIA_ROOT-relative path of the stored asset.",
    )
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    byte_size = models.BigIntegerField(default=0)
    mime_type = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=16,
        choices=AssetStatus.choices,
        default=AssetStatus.PENDING,
        db_index=True,
    )
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["bundle", "status"]),
            models.Index(fields=["entity_kind", "legacy_id"]),
            models.Index(fields=["sha256"]),
        ]
        verbose_name = "Migration asset"
        verbose_name_plural = "Migration assets"

    def __str__(self) -> str:
        return f"{self.entity_kind}/{self.legacy_id}.{self.asset_kind} [{self.status}]"


class MigrationProgressEvent(models.Model):
    """Append-only timeline of progress events for the DAG view and SSE stream.

    The orchestrator + pipeline emit one row per stage transition (and one
    per N rows for big artifacts) so the UI can stream live progress.
    Bounded retention: the cleanup management command prunes events older
    than 30 days.
    """

    KIND_CHOICES = [
        ("stage_started", "Stage started"),
        ("stage_finished", "Stage finished"),
        ("artifact_progress", "Artifact progress"),
        ("rollback", "Rollback"),
        ("warning", "Warning"),
        ("info", "Info"),
    ]

    bundle = models.ForeignKey(
        MigrationBundle,
        on_delete=models.CASCADE,
        related_name="progress_events",
    )
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, db_index=True)
    stage = models.CharField(max_length=32, blank=True, db_index=True)
    message = models.TextField(blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["bundle", "created_at"]),
            models.Index(fields=["bundle", "stage"]),
        ]
        verbose_name = "Migration progress event"
        verbose_name_plural = "Migration progress events"

    def __str__(self) -> str:
        return f"[{self.kind}] {self.stage or '-'}: {self.message[:60]}"


class ConflictResolution(models.TextChoices):
    PENDING = "PENDING", "Pending operator review"
    OVERWRITE = "OVERWRITE", "Overwrite existing"
    PRESERVE = "PRESERVE", "Preserve existing (skip)"
    MERGE = "MERGE", "Merge fields"


class MigrationConflict(models.Model):
    """Upsert conflict that surfaced during apply — operator review surface.

    Created when a lander would `update_or_create` an existing row whose
    canonical-field values disagree with the inbound row. Replaces silent
    overwrite — the operator sees the diff and chooses overwrite / preserve /
    merge before the lander commits.
    """

    bundle = models.ForeignKey(
        MigrationBundle,
        on_delete=models.CASCADE,
        related_name="conflicts",
    )
    domain = models.CharField(max_length=32, db_index=True)
    canonical_model = models.CharField(max_length=128, db_index=True)
    canonical_pk = models.CharField(max_length=64, db_index=True)
    legacy_id = models.CharField(max_length=128, db_index=True, blank=True)
    existing_values = models.JSONField(default=dict, blank=True)
    incoming_values = models.JSONField(default=dict, blank=True)
    changed_fields = models.JSONField(default=list, blank=True)
    resolution = models.CharField(
        max_length=16,
        choices=ConflictResolution.choices,
        default=ConflictResolution.PENDING,
        db_index=True,
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_migration_conflicts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["bundle", "resolution"]),
            models.Index(fields=["canonical_model", "canonical_pk"]),
        ]
        verbose_name = "Migration conflict"
        verbose_name_plural = "Migration conflicts"

    def __str__(self) -> str:
        return f"{self.canonical_model}#{self.canonical_pk} [{self.resolution}]"


class FinancialMismatchError(Exception):
    """Raised by the financial guardrail when expected totals diverge from observed."""


# ─── v3.29 REST API completion — scoped tokens + outbound webhooks ──────────


class MigrationCloudAPIToken(models.Model):
    """Opaque scoped API token for the Migration Cloud REST API.

    Plaintext is generated server-side and returned **once** in the mint
    response body. We persist only ``sha256(token)`` so a database leak
    cannot replay a token (constant-time compare on lookup defends
    against timing oracles).

    Scopes follow the ``<resource>:<action>`` convention:
        bundles:read / bundles:write / templates:read /
        artifacts:write / reconcile:run / tokens:manage / webhooks:manage.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="migration_cloud_api_tokens",
        help_text="User this token authenticates as.",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="sha256 hex digest of the opaque token; plaintext returned ONCE at mint.",
    )
    name = models.CharField(
        max_length=128,
        help_text="Operator/partner-supplied label for token identification in the UI.",
    )
    scopes = models.JSONField(
        default=list,
        blank=True,
        help_text="List of scope strings, e.g. ['bundles:read', 'bundles:write'].",
    )
    tenant_scope = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="migration_cloud_api_tokens",
        help_text="Optional tenant-binding. Null = all tenants the user can access.",
    )
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # v3.32.0 — token rotation: link a revoked token to its successor + 7-day grace.
    rotated_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rotated_from",
        help_text=(
            "When this token was rotated, points to the new successor row. "
            "Audit trail only; does not affect auth decisions."
        ),
    )
    grace_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "When set, the (revoked) token still authenticates until this "
            "instant — operator's 7-day client-rollout window."
        ),
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Migration Cloud API token"
        verbose_name_plural = "Migration Cloud API tokens"

    def __str__(self) -> str:
        return f"{self.name} (user={self.user_id})"

    @property
    def is_active(self) -> bool:
        """Return True when neither revoked nor expired."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            return self.expires_at > timezone.now()
        return True


class MigrationCloudWebhookSubscription(models.Model):
    """Partner-registered outbound webhook endpoint.

    Tenant-scoped: every subscription belongs to one school; webhook
    dispatch fans out across (tenant, event_type) tuples so an event
    on Bundle A in School X doesn't reach School Y's listeners.
    """

    tenant = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_cloud_webhook_subscriptions",
    )
    url = models.URLField(
        max_length=512,
        help_text="HTTPS endpoint the platform POSTs delivery payloads to.",
    )
    secret_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="sha256 hex digest of the HMAC secret (verification aid only).",
    )
    # Encrypted-at-rest via apps.accounts.legacy_hashes.encryption.EncryptedBinaryField (v3.32.0)
    secret_ciphertext = _webhook_encrypt_binaryfield(
        null=True,
        blank=True,
        help_text=(
            "HMAC secret material used to sign outbound webhook "
            "deliveries. Encrypted at rest via the Fernet shim; reads "
            "transparently decrypt at the dispatcher. NEVER log."
        ),
    )
    event_types = models.JSONField(
        default=list,
        blank=True,
        help_text="List of event-type strings, e.g. ['bundle.advanced'].",
    )
    # v3.33.0 — coarse event-class opt-in. The dispatcher consults this
    # BEFORE event_types: a subscription only receives events whose
    # ``"<class>.*"`` glob is listed here. Empty list (the literal
    # default for JSON-field-backed columns) is treated by the
    # dispatcher as ``["migration.*"]`` so legacy v3.32 subscriptions
    # remain on the migration-only firehose with zero migration writes
    # to existing rows. Schoolops cross-app events publish under
    # ``"schoolops.*"`` and skip subscriptions that haven't opted in.
    event_classes = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of event-class globs the subscription opts in to. "
            "Examples: ['migration.*'], ['migration.*', 'schoolops.*']. "
            "Empty list is treated as ['migration.*'] (legacy default)."
        ),
    )
    active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_cloud_webhook_subscriptions",
    )
    last_delivery_status = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Migration Cloud webhook subscription"
        verbose_name_plural = "Migration Cloud webhook subscriptions"

    def __str__(self) -> str:
        return f"{self.url} [{'active' if self.active else 'inactive'}]"


class WebhookDeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    EXHAUSTED = "exhausted", "Exhausted"


class MigrationCloudWebhookDelivery(AppendOnlyModelMixin, models.Model):
    objects = AppendOnlyManager()

    """Append-only delivery log for outbound webhooks.

    FSM: ``pending`` → (HTTP 2xx) ``delivered``
                     → (transient failure + retries remain) ``failed`` /
                       still ``pending`` for next attempt at ``next_retry_at``
                     → (retries exhausted) ``exhausted``.

    Retry schedule: 1m → 5m → 30m → 2h → 12h → 24h then ``exhausted``.
    """

    subscription = models.ForeignKey(
        MigrationCloudWebhookSubscription,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event_type = models.CharField(max_length=64, db_index=True)
    payload_json = models.JSONField(default=dict)
    request_signature = models.CharField(
        max_length=128,
        blank=True,
        help_text="hex HMAC-SHA256(secret, payload_json_canonical_bytes).",
    )
    attempt_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=WebhookDeliveryStatus.choices,
        default=WebhookDeliveryStatus.PENDING,
        db_index=True,
    )
    last_response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    # v3.32.0 — per-tenant delivery quotas. When the tenant's hourly quota
    # is exhausted, dispatcher defers the row to the next-hour boundary
    # instead of attempting + counting it against the retry FSM.
    deferred_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "When the dispatcher skipped this row due to a per-tenant rate "
            "limit, the wall-clock instant it becomes eligible again. The "
            "row's status remains 'pending' — attempt_count is NOT bumped."
        ),
    )
    deferred_reason = models.CharField(
        max_length=64,
        blank=True,
        help_text="Short code: 'tenant-quota-exhausted', 'tenant-quota-warning', etc.",
    )
    # v3.35.0 — caller-supplied idempotency key for collision guard.
    # When the dispatcher's ``enqueue`` is called twice within 24h with
    # the same ``(subscription_id, idempotency_key)`` we short-circuit
    # the second call and return the existing row. Empty string ("") is
    # the legacy default — collision guard is skipped for those rows so
    # v3.32+ enqueue sites that don't pass a key keep working unchanged.
    idempotency_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "Caller-supplied idempotency key. Two enqueues within 24h "
            "carrying the same (subscription, idempotency_key) produce "
            "only one delivery row. Empty string disables the guard."
        ),
    )
    # v3.35.0 — operator-triggered replay link. When the operator clicks
    # "Replay" in the audit view (``views_webhook_admin.WebhookDelivery
    # ReplayView``) a NEW delivery row is created that copies payload +
    # event_type + signature material from the original; this FK points
    # back to the original row so the audit log can trace causality.
    # ``on_delete=SET_NULL`` keeps the replay row visible even if the
    # original is later purged.
    replay_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replays",
        db_index=True,
        help_text=(
            "FK to the original delivery this row replays. NULL for "
            "first-attempt deliveries; populated only via operator replay."
        ),
    )
    replayed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="webhook_replays_triggered",
        help_text="Staff user who triggered this replay (NULL for non-replay rows).",
    )
    replayed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this replay row was created (operator click time).",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Migration Cloud webhook delivery"
        verbose_name_plural = "Migration Cloud webhook deliveries"
        indexes = [
            # v3.35.0 — composite index supports the duplicate-replay-window
            # guard (lookup by (replay_of_id, created_at)) and the idempotency
            # key collision guard (lookup by (subscription_id, idempotency_key)).
            models.Index(
                fields=["replay_of", "created_at"],
                name="mc_webhook_replay_of_idx",
            ),
            models.Index(
                fields=["subscription", "idempotency_key"],
                name="mc_webhook_sub_idem_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} → sub={self.subscription_id} [{self.status}]"


# ─── Companion receiver + MAA (v3.29 Agent 2) ────────────────────────────
#
# Companion browser-extension uploads canonical bundles from inside the
# customer's authenticated competitor-SIS session. Two trust primitives
# gate every upload:
#   1. MigrationAuthorizationAgreement — operator's signed consent that
#      they have legal authority over the source data (vendor data-
#      portability authorization).
#   2. CompanionUploadReceipt — append-only record of every accepted
#      upload (bundle FK + MAA FK + ciphertext sha256 + idempotency key).
# Defense in depth: bundles are CLIENT-SIDE encrypted by the extension
# (libsodium sealed-box, X25519 + XSalsa20-Poly1305) before leaving the
# browser. The server stores ciphertext until a staff-driven decrypt
# hook runs in-memory with the private-key half (NEVER persisted).


class MigrationAuthorizationAgreement(models.Model):
    """Operator-signed authorization that they have legal right to migrate
    the source-vendor data. Required BEFORE any companion upload is
    accepted; revocation freezes future uploads for the same tenant +
    vendor pair but does NOT retroactively invalidate accepted bundles.
    """

    tenant = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="migration_authorization_agreements",
        help_text="Tenant the agreement covers. Matches CompanionUploadReceipt.tenant.",
    )
    signed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="migration_authorization_agreements_signed",
    )
    signed_by_role = models.CharField(
        max_length=128,
        help_text="Operator-supplied role (e.g. 'Head of School', 'IT Director').",
    )
    vendor_source = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Source-vendor id (matches Companion canonical-bundle 'source' field).",
    )
    vendor_account_holder_name = models.CharField(
        max_length=256,
        help_text="Human with legal authority over the source data at the vendor.",
    )
    signed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    agreement_version = models.CharField(max_length=32, default="v1.0")
    signature_text = models.TextField(
        help_text="Verbatim text the operator agreed to; rendered at sign time.",
    )
    # v3.33.0 — audit-grade fingerprint of the signature_text bytes.
    # sha256 hex digest (64 chars). Auto-computed on save so the row's
    # fingerprint is always in lock-step with the verbatim text. NEVER
    # log this value outside the staff-only audit endpoints — although
    # it is one-way and reveals no secret, conservative defense keeps
    # it inside the audit boundary.
    signature_text_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "sha256(signature_text.encode('utf-8')) — audit fingerprint, "
            "auto-computed on save. Detects post-hoc tampering."
        ),
    )
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        app_label = "migration_cloud"
        ordering = ["-signed_at"]
        indexes = [
            models.Index(fields=["tenant", "-signed_at"]),
            models.Index(fields=["tenant", "vendor_source"]),
            models.Index(fields=["vendor_source", "-signed_at"]),
        ]
        verbose_name = "Migration authorization agreement"
        verbose_name_plural = "Migration authorization agreements"

    def __str__(self) -> str:
        state = "revoked" if self.revoked_at else "active"
        return f"MAA[{self.agreement_version}] {self.vendor_source} ({state})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def save(self, *args, **kwargs) -> None:
        """Auto-compute ``signature_text_sha256`` on every save.

        Pure-function fingerprint of the verbatim text; keeps the
        audit column in lock-step with the body even if a future
        admin tool edits the text post-create. sha256 over the
        canonical UTF-8 bytes of ``signature_text``.
        """
        import hashlib

        canonical = (self.signature_text or "").encode("utf-8")
        self.signature_text_sha256 = hashlib.sha256(canonical).hexdigest()
        super().save(*args, **kwargs)


class CompanionCiphertextBlob(models.Model):
    """Encrypted bundle bytes received from a Companion upload.

    Stored as a Django ``FileField`` (default storage) rather than
    ``BinaryField`` so very large bundles don't bloat the DB row. Bytes
    are NEVER logged; only sha256 + size appear in logs.
    """

    tenant = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="companion_ciphertext_blobs",
    )
    blob_file = models.FileField(
        upload_to="companion_uploads/",
        help_text="Encrypted bundle bytes; layout: companion_uploads/<tenant_id>/<uuid>.bin",
    )
    ciphertext_sha256 = models.CharField(max_length=64, db_index=True)
    byte_size = models.PositiveBigIntegerField(default=0)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    decrypted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "migration_cloud"
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["tenant", "-received_at"]),
            models.Index(fields=["ciphertext_sha256"]),
        ]
        verbose_name = "Companion ciphertext blob"
        verbose_name_plural = "Companion ciphertext blobs"

    def __str__(self) -> str:
        return f"Blob[{self.ciphertext_sha256[:12]}] {self.byte_size}B"


class CompanionUploadReceipt(models.Model):
    """Append-only record of every accepted Companion upload.

    Links a ``MigrationBundle`` (the wizard-pipeline handle) to its
    ``MigrationAuthorizationAgreement`` (legal consent) and the
    ``CompanionCiphertextBlob`` storing the encrypted payload. Replays
    of the same ``client_idempotency_key`` return the previous receipt
    rather than creating a new bundle.
    """

    tenant = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="companion_upload_receipts",
    )
    bundle = models.ForeignKey(
        MigrationBundle,
        on_delete=models.CASCADE,
        related_name="companion_receipts",
    )
    maa = models.ForeignKey(
        MigrationAuthorizationAgreement,
        on_delete=models.PROTECT,
        related_name="companion_receipts",
    )
    ciphertext_blob = models.ForeignKey(
        CompanionCiphertextBlob,
        on_delete=models.PROTECT,
        related_name="receipts",
    )
    client_idempotency_key = models.CharField(max_length=128, unique=True)
    ciphertext_sha256 = models.CharField(max_length=64, db_index=True)
    plaintext_byte_size = models.PositiveIntegerField(
        default=0,
        help_text="Client-reported plaintext size (post-decrypt, pre-compression).",
    )
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    encryption_scheme = models.CharField(
        max_length=32,
        default="libsodium-secretbox-x25519-sealed",
        help_text="Encryption scheme tag; matches companion-extension/src/lib/crypto.ts.",
    )
    # v3.33.0 — Server keypair version that successfully decrypted this
    # upload. Filled by ``CompanionDecryptHookView`` after the SealedBox
    # opens; empty string until the decrypt hook runs. Lets an auditor
    # answer "which active-at-the-time keypair half opened receipt R?"
    # without replaying the rotation history.
    key_version = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text=(
            "Server keypair version that successfully decrypted this "
            "upload (filled at decrypt time). Empty until the decrypt "
            "hook runs. NEVER carries private bytes."
        ),
    )

    class Meta:
        app_label = "migration_cloud"
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["tenant", "-received_at"]),
            models.Index(fields=["bundle"]),
            models.Index(fields=["received_at"]),
        ]
        verbose_name = "Companion upload receipt"
        verbose_name_plural = "Companion upload receipts"

    def __str__(self) -> str:
        return f"Receipt[{self.client_idempotency_key[:12]}] bundle={self.bundle_id}"


class MigrationCloudCompanionKeypair(models.Model):
    """Server-side X25519 keypair used to seal/open Companion bundles.

    The Companion fetches the public half via
    ``GET /companion/server-pubkey/`` and seals the canonical bundle
    against it (libsodium ``crypto_box_seal`` — see
    ``companion-extension/src/lib/crypto.ts``). The encrypted bytes ride
    multipart to ``/companion/upload/`` and are decrypted in-process by
    ``CompanionDecryptHookView`` using the matching private half kept
    HERE.

    v3.34.0 — keypairs are now PER-TENANT. Exactly one row per tenant
    carries ``is_active=True`` at any time (enforced by the partial
    unique constraint scoped to ``(tenant, is_active=True)``). Each
    tenant's rotation cycle is independent: a leaked key in tenant A
    triggers rotation of tenant A's keypair only — tenant B's blast
    radius is zero. Operator UX is invisible: the popup fetches the
    pubkey for the current operator's tenant via the session cookie.

    Security invariants:

    * ``private_key_encrypted`` is wrapped via the
      :class:`~apps.accounts.legacy_hashes.encryption.EncryptedBinaryField`
      Fernet shim. The private bytes NEVER appear in a response, in
      logs, or in admin list_display.
    * Constant-time compare is used for any external fingerprint check.
    * Public-key fingerprint is sha256(public_key_b64)[:16] bytes,
      base64-encoded — never the full hash (truncation prevents
      accidental disclosure of the full pubkey to logging sinks that
      don't carry the public_key_b64 itself).
    * Tenant FK is mandatory at v3.34.0; the v3.32-era global keypair
      was migrated forward to the first tenant via migration
      ``0015_companion_keypair_per_tenant``.
    """

    KEY_VERSION_MAX_LEN = 16
    PUBLIC_KEY_B64_MAX_LEN = 64

    # tenant-isolation-allow: per-tenant-server-keypair-rotation-scope
    tenant = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="companion_keypairs",
        db_index=True,
        help_text=(
            "Tenant that owns this keypair. v3.34.0 promotes the "
            "Companion server keypair from platform-global to per-tenant "
            "so a single-tenant key leak does not blast-radius the rest."
        ),
    )
    key_version = models.CharField(
        max_length=KEY_VERSION_MAX_LEN,
        db_index=True,
        help_text=(
            "Monotonic version tag scoped per-tenant, e.g. 'v1', 'v2'. "
            "Unique within (tenant, key_version)."
        ),
    )
    public_key_b64 = models.CharField(
        max_length=PUBLIC_KEY_B64_MAX_LEN,
        help_text="Base64 of the 32-byte X25519 public key; safe to return.",
    )
    # ``EncryptedBinaryField`` — Fernet-wrapping shim that round-trips
    # bytes transparently. Reads return the raw 32-byte private key
    # the SealedBox opener needs; writes encrypt on the way out. The
    # DB column shape (BinaryField backing) is unchanged. Wrap promoted
    # from v3.32's plain BinaryField via migration 0011.
    private_key_encrypted = _EncryptedBinaryField(
        help_text="Encrypted X25519 private key. Never returned in responses.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    rotated_out_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "migration_cloud"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["key_version"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["tenant", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "is_active"],
                condition=models.Q(is_active=True),
                name="uniq_active_keypair_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key_version"],
                name="uniq_keypair_version_per_tenant",
            ),
        ]
        verbose_name = "Migration Cloud companion keypair"
        verbose_name_plural = "Migration Cloud companion keypairs"

    def __str__(self) -> str:
        flag = "active" if self.is_active else "retired"
        return f"CompanionKeypair[{self.key_version}] tenant={self.tenant_id} ({flag})"


# ─── v3.35.0 — MAA v2.0 flip pre-flight tooling (Agent 3) ────────────────
#
# Two append-only audit models supporting the MAA v2.0 promotion path.
# Neither carries a tenant FK because both records are platform-wide
# concerns (counsel signoff is per-platform; the re-sign campaign is
# tracked at the platform level so a single send-attempt counts even
# if the operator changes tenant context between dispatches).
#
# Both models are append-only by convention — there are NO UPDATE or
# DELETE code paths exposed in the codebase. Admin / mgmt commands
# call ``.objects.create(...)`` only.


class MigrationCloudCounselAttestation(models.Model):
    """Append-only audit record of counsel attestations.

    Each row records an explicit operator-level attestation that
    external counsel has signed off on a numbered MAA promotion
    artifact (or other compliance gate). Operators with the
    ``legal-officers`` staff group attach attestations from the
    operator UI; the model is append-only and platform-wide.

    Security invariants:

    * Append-only: the operator UI never offers an update / delete
      affordance, and the admin entry registered in ``admin.py`` is
      ``has_change_permission=False`` / ``has_delete_permission=False``.
    * ``attestation_text`` is operator-supplied prose; it does NOT
      include MAA body text (the verifier checks readiness without
      logging the body). Treated as low-sensitivity narrative.
    * Platform-wide (no tenant FK): counsel signoff is a platform
      concern, not a per-tenant one. Marker below makes the
      cross-tenant scope explicit for the tenant-isolation scanner.
    """

    ATTESTATION_TYPE_MAX_LEN = 64
    RELATED_ARTIFACT_PATH_MAX_LEN = 512

    # tenant-isolation-allow: platform-wide-counsel-attestation-audit-log
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="migration_cloud_counsel_attestations",
        help_text=(
            "Staff user who recorded this attestation. Must be a member "
            "of the legal-officers group at attestation time."
        ),
    )
    attested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    attestation_type = models.CharField(
        max_length=ATTESTATION_TYPE_MAX_LEN,
        db_index=True,
        help_text=(
            "Stable identifier for the attestation kind, e.g. "
            "'maa_v2_counsel_signoff_received'. Keep short, machine-readable."
        ),
    )
    attestation_text = models.TextField(
        help_text=(
            "Operator-supplied narrative describing the attestation "
            "(e.g. 'Received signed PDF from counsel Jane Q. Doe, "
            "Esq. on 2026-06-01; filed at docs/legal/maa_v2_signoff.pdf')."
        ),
    )
    related_artifact_path = models.CharField(
        max_length=RELATED_ARTIFACT_PATH_MAX_LEN,
        blank=True,
        default="",
        help_text=(
            "Optional repo-relative path of the supporting artifact "
            "(e.g. 'docs/legal/maa_v2_signoff.pdf'). Free-text; the "
            "audit row is the SOT, not the file."
        ),
    )

    class Meta:
        app_label = "migration_cloud"
        ordering = ["-attested_at"]
        indexes = [
            models.Index(fields=["attestation_type", "-attested_at"]),
        ]
        verbose_name = "Migration Cloud counsel attestation"
        verbose_name_plural = "Migration Cloud counsel attestations"

    def __str__(self) -> str:
        return (
            f"CounselAttestation[{self.attestation_type}] "
            f"operator={self.operator_id} at={self.attested_at:%Y-%m-%d}"
        )


class MigrationCloudMAACampaignNotification(models.Model):
    """Idempotency record for MAA v2.0 re-sign campaign emails.

    Each row records one (agreement, recipient_email) pair that has
    been notified for the named campaign. The
    ``maa_v2_resign_campaign`` mgmt command checks this table before
    enqueueing a fresh email — operators can re-run the command
    daily / weekly without double-sending.

    Append-only: no UPDATE / DELETE paths; bare ``.objects.create``
    only. Cross-tenant by design (the campaign is run platform-wide
    by the partner-success team) — marker is 5-part hyphenated.
    """

    AGREEMENT_VERSION_MAX_LEN = 32
    RECIPIENT_EMAIL_MAX_LEN = 254  # RFC 5321 path-segment cap.
    CAMPAIGN_VERSION_MAX_LEN = 32

    # tenant-isolation-allow: cross-tenant-maa-campaign-tracking
    agreement = models.ForeignKey(
        MigrationAuthorizationAgreement,
        on_delete=models.CASCADE,
        related_name="campaign_notifications",
        help_text=(
            "The v1.0-era MAA row that triggered the notification. "
            "On agreement deletion the notification rows cascade out "
            "(they are derived audit; the SOT is the agreement)."
        ),
    )
    recipient_email = models.EmailField(
        max_length=RECIPIENT_EMAIL_MAX_LEN,
        help_text=(
            "Email address that received (or was queued to receive) "
            "the campaign email. Operator-attached not at scrape time "
            "but resolved from the signing operator's User row."
        ),
    )
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)
    campaign_version = models.CharField(
        max_length=CAMPAIGN_VERSION_MAX_LEN,
        db_index=True,
        help_text=(
            "Campaign identifier, e.g. 'maa_v2_resign_2026Q3'. Allows "
            "future v3.x re-sign campaigns to coexist (each campaign "
            "is independently idempotent)."
        ),
    )
    dispatch_mode = models.CharField(
        max_length=16,
        default="dry_run",
        db_index=True,
        help_text=(
            "Either 'dry_run' (recorded but not enqueued) or 'queued' "
            "(enqueued via send_mail and recorded). 'queued' rows are "
            "the only ones operators expect a real email send for."
        ),
    )

    class Meta:
        app_label = "migration_cloud"
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["agreement", "recipient_email", "campaign_version"],
                name="uniq_maa_campaign_per_agreement_recipient",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign_version", "-sent_at"]),
            models.Index(fields=["dispatch_mode", "-sent_at"]),
        ]
        verbose_name = "Migration Cloud MAA campaign notification"
        verbose_name_plural = "Migration Cloud MAA campaign notifications"

    def __str__(self) -> str:
        return (
            f"MAACampaign[{self.campaign_version}] "
            f"agreement={self.agreement_id} "
            f"mode={self.dispatch_mode}"
        )


# v3.38.0 Agent 5 — tamper-evident append-only audit log.
# Implementation lives in ``models_audit`` to keep this file focused on
# the bundle/artifact/run/api/webhook lifecycle models; re-exported here
# so Django's app loader and downstream callers can keep importing from
# ``apps.migration_cloud.models``.
from apps.migration_cloud.models_audit import (  # noqa: E402, F401
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
    MigrationCloudAuditEventReadOnlyError,
    AuditEventManager,
)

# v3.40.0 Agent 7 — customer-facing migration intake request.
# Lives in its own module to keep this file focused on the existing
# bundle/artifact/run/api/webhook/audit lifecycle. Re-exported here so
# Django's app loader picks up the model and migrations resolve it.
from apps.migration_cloud.models_intake import (  # noqa: E402, F401
    MigrationIntakeRequest,
    MigrationIntakeState,
    MigrationIntakeStateError,
)

# v3.40.0 Agent 15 — MAA v2.0 counsel-activate singleton state.
# Persists the operator's counsel-signoff flip from v1.0 to v2.0 across
# worker restarts. See ``apps/migration_cloud/models_maa_state.py``.
from apps.migration_cloud.models_maa_state import (  # noqa: E402, F401
    MAAActiveVersionState,
    MAAAlreadyActiveError,
)
