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

# v3.32.0 — encrypted-at-rest BinaryField for the webhook subscription
# secret_ciphertext column. Shares the Fernet key with the User-model
# legacy_* columns so a single key rotation covers both surfaces — see
# docs/SECURITY_KEYS.md.
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
            models.UniqueConstraint(
                fields=["legacy_namespace", "legacy_id", "canonical_model", "school"],
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


class MigrationCloudWebhookDelivery(models.Model):
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

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Migration Cloud webhook delivery"
        verbose_name_plural = "Migration Cloud webhook deliveries"

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

    Exactly one row carries ``is_active=True`` at any time (enforced by
    the unique partial constraint). Rotation cycles the active flag and
    stamps ``rotated_out_at`` on the previous row so older ciphertext
    blobs can still be decrypted by version. Operator UX is invisible:
    the popup re-fetches per-session and switches keys automatically.

    Security invariants:

    * ``private_key_encrypted`` is wrapped via Agent 5's
      ``EncryptedCharField`` shim when importable; otherwise it stores
      raw bytes with a ``# crypto-pending`` marker (Agent 5 wraps in a
      follow-up migration). Either way, the private bytes NEVER appear
      in a response, in logs, or in admin list_display.
    * Constant-time compare is used for any external fingerprint check.
    * Public-key fingerprint is sha256(public_key_b64)[:16] bytes,
      base64-encoded — never the full hash (truncation prevents
      accidental disclosure of the full pubkey to logging sinks that
      don't carry the public_key_b64 itself).
    """

    KEY_VERSION_MAX_LEN = 16
    PUBLIC_KEY_B64_MAX_LEN = 64

    key_version = models.CharField(
        max_length=KEY_VERSION_MAX_LEN,
        unique=True,
        db_index=True,
        help_text="Monotonic version tag, e.g. 'v1', 'v2'.",
    )
    public_key_b64 = models.CharField(
        max_length=PUBLIC_KEY_B64_MAX_LEN,
        help_text="Base64 of the 32-byte X25519 public key; safe to return.",
    )
    # ``BinaryField`` rather than CharField — the encrypted private bytes
    # are not human-readable. When Agent 5's EncryptedCharField shim is
    # importable, the bytes are stored Fernet-wrapped; otherwise they
    # are raw NaCl PrivateKey.encode() bytes.
    private_key_encrypted = models.BinaryField(
        help_text="Encrypted X25519 private key. Never returned in responses.",
        # crypto-pending: wrap-after-cross-agent-merge
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
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="migrationcloud_companion_keypair_one_active",
            ),
        ]
        verbose_name = "Migration Cloud companion keypair"
        verbose_name_plural = "Migration Cloud companion keypairs"

    def __str__(self) -> str:
        flag = "active" if self.is_active else "retired"
        return f"CompanionKeypair[{self.key_version}] ({flag})"
