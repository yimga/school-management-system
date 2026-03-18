"""
Package engine models: InstalledPackage, PackageVersion, PackageChangeLog (metadata plan todo 5).
Canonical package format is documented in docs/architecture/PACKAGE_FORMAT.md.
"""

from django.db import models


class InstalledPackage(models.Model):
    """A package (blueprint/workflow/dashboard/policy/theme pack) installed for a tenant or scope."""

    PACKAGE_TYPES = [
        ("blueprint", "Blueprint Pack"),
        ("workflow", "Workflow Pack"),
        ("dashboard", "Dashboard Pack"),
        ("policy", "Policy Bundle"),
        ("theme", "Theme Pack"),
    ]

    package_id = models.CharField(
        max_length=120, db_index=True, help_text="Stable package identifier."
    )
    package_type = models.CharField(
        max_length=40, choices=PACKAGE_TYPES, default="blueprint"
    )
    version = models.CharField(max_length=80, help_text="Installed version string.")
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="Null = platform/global install.",
    )
    scope = models.CharField(
        max_length=20,
        default="tenant",
        choices=[
            ("platform", "Platform"),
            ("region", "Region"),
            ("blueprint", "Blueprint"),
            ("plan", "Plan"),
            ("tenant", "Tenant"),
            ("sandbox", "Sandbox"),
        ],
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    applied_by_id = models.IntegerField(null=True, blank=True)
    rollback_token = models.CharField(max_length=64, blank=True, db_index=True)
    dependency_snapshot = models.JSONField(default=list, blank=True)
    impact_summary = models.JSONField(default=dict, blank=True)
    apply_stage = models.CharField(
        max_length=20,
        choices=[
            ("sandbox", "Sandbox"),
            ("test", "Test"),
            ("production", "Production"),
            ("rollback", "Rollback"),
            ("promoted", "Promoted"),
        ],
        default="production",
    )
    reconciliation_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("applied", "Applied"),
            ("reconciled", "Reconciled"),
            ("rolled_back", "Rolled Back"),
            ("promoted", "Promoted"),
            ("failed", "Failed"),
        ],
        default="pending",
    )
    promoted_from_mode = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "packages"
        verbose_name = "Installed Package"
        verbose_name_plural = "Installed Packages"
        ordering = ["-applied_at"]
        unique_together = [["package_id", "version", "school"]]

    def __str__(self):
        return f"{self.package_id}@{self.version} ({self.scope})"


class PackageVersion(models.Model):
    """Known package version metadata (id, version, compatibility, payload sections)."""

    package_id = models.CharField(max_length=120, db_index=True)
    version = models.CharField(max_length=80)
    dependencies = models.JSONField(
        default=list, blank=True, help_text="Package dependencies."
    )
    compatibility = models.JSONField(
        default=dict, blank=True, help_text="Platform/region constraints."
    )
    payload_sections = models.JSONField(
        default=dict,
        blank=True,
        help_text="Blueprint/workflow/dashboard/policy/theme payloads.",
    )
    impact_summary = models.JSONField(
        default=dict, blank=True, help_text="Computed impact preview snapshot."
    )
    changelog_summary = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "packages"
        verbose_name = "Package Version"
        verbose_name_plural = "Package Versions"
        unique_together = [["package_id", "version"]]
        ordering = ["package_id", "-created_at"]

    def __str__(self):
        return f"{self.package_id}@{self.version}"


class PackageChangeLog(models.Model):
    """Audit trail for package apply/rollback (actor, package, tenant, mode, token)."""

    package_id = models.CharField(max_length=120, db_index=True)
    version = models.CharField(max_length=80)
    school_id = models.UUIDField(null=True, blank=True, db_index=True)
    mode = models.CharField(
        max_length=20,
        choices=[
            ("sandbox", "Sandbox"),
            ("test", "Test"),
            ("production", "Production"),
        ],
        default="production",
    )
    action = models.CharField(
        max_length=20,
        choices=[("apply", "Apply"), ("rollback", "Rollback"), ("promote", "Promote")],
        default="apply",
    )
    rollback_token = models.CharField(max_length=64, blank=True, db_index=True)
    actor_id = models.IntegerField(null=True, blank=True)
    dependency_snapshot = models.JSONField(default=list, blank=True)
    impact_summary = models.JSONField(default=dict, blank=True)
    reconciliation_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("applied", "Applied"),
            ("reconciled", "Reconciled"),
            ("rolled_back", "Rolled Back"),
            ("promoted", "Promoted"),
            ("failed", "Failed"),
        ],
        default="pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "packages"
        verbose_name = "Package Change Log"
        verbose_name_plural = "Package Change Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.package_id}@{self.version} {self.created_at}"


class ExperiencePack(models.Model):
    """
    Phase 10 — 10.1: Theme & Experience as packageable unit.
    Theme + layout + dashboard visual + communication style. Runtime-only theme resolution; compare/rollback.
    """

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    theme_pack_id = models.IntegerField(
        null=True, blank=True, help_text="FK to ThemePack when migrated."
    )
    layout_schema = models.JSONField(default=dict, blank=True)
    communication_style = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "packages"
        verbose_name = "Experience Pack"
        verbose_name_plural = "Experience Packs"
        ordering = ["code"]

    def __str__(self):
        return self.name or self.code


class DocumentPack(models.Model):
    """
    Phase 10 — 10.4: Document Library. Pack of documents with lifecycle states and retention rules.
    Lifecycle states (draft → review → approved → archived); retention_rule for auto-archival/expiry.
    """

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    lifecycle_states = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered list of state codes, e.g. ['draft', 'review', 'approved', 'archived'].",
    )
    retention_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text='Retention policy: e.g. {"archive_after_days": 365, "expire_after_days": null}.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "packages"
        verbose_name = "Document Pack"
        verbose_name_plural = "Document Packs"
        ordering = ["code"]

    def __str__(self):
        return self.name or self.code
