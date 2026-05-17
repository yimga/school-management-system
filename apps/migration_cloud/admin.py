"""Unfold admin registration for Migration Cloud (Phase U1).

Operator-only surfaces; the rich wizard ships in Phase U6. These admin pages
are the minimum viable inspection surface until the bespoke control-plane
template lands.
"""

from __future__ import annotations

from django.contrib import admin
from config.admin import platform_admin_site

from .models import (
    MigrationArtifact,
    MigrationAsset,
    MigrationBundle,
    MigrationConflict,
    MigrationIdMapping,
    MigrationProgressEvent,
)


@admin.register(MigrationBundle, site=platform_admin_site)
class MigrationBundleAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "school",
        "intake_method",
        "status",
        "sla_tier",
        "artifact_count",
        "created_at",
    )
    list_filter = ("status", "intake_method", "sla_tier")
    search_fields = ("label", "idempotency_key", "intake_source_uri", "source_hint")
    readonly_fields = (
        "idempotency_key",
        "size_summary",
        "discovery_summary",
        "mapping_summary",
        "reconciliation_summary",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    )
    date_hierarchy = "created_at"


@admin.register(MigrationArtifact, site=platform_admin_site)
class MigrationArtifactAdmin(admin.ModelAdmin):
    list_display = (
        "path_within_bundle",
        "bundle",
        "detected_format",
        "byte_size",
        "row_count",
        "inferred_source",
        "quarantined",
    )
    list_filter = ("detected_format", "quarantined", "inferred_source")
    search_fields = ("filename", "path_within_bundle", "sha256")
    readonly_fields = (
        "sha256",
        "byte_size",
        "row_count",
        "column_count",
        "encoding",
        "locale_hints",
        "profile",
        "inferred_source",
        "inferred_domain",
        "created_at",
        "updated_at",
    )
    raw_id_fields = ("bundle", "parent_archive")


@admin.register(MigrationIdMapping, site=platform_admin_site)
class MigrationIdMappingAdmin(admin.ModelAdmin):
    list_display = ("legacy_namespace", "legacy_id", "canonical_model", "canonical_pk",
                    "domain", "school", "bundle", "created_at")
    list_filter = ("legacy_namespace", "domain", "canonical_model")
    search_fields = ("legacy_id", "canonical_pk", "canonical_model")
    raw_id_fields = ("bundle", "school")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


@admin.register(MigrationAsset, site=platform_admin_site)
class MigrationAssetAdmin(admin.ModelAdmin):
    list_display = ("entity_kind", "legacy_id", "asset_kind", "status",
                    "byte_size", "school", "bundle", "created_at")
    list_filter = ("status", "entity_kind", "asset_kind")
    search_fields = ("legacy_id", "source_uri", "stored_path", "sha256")
    raw_id_fields = ("bundle", "school")
    readonly_fields = ("sha256", "byte_size", "stored_path", "created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(MigrationProgressEvent, site=platform_admin_site)
class MigrationProgressEventAdmin(admin.ModelAdmin):
    list_display = ("bundle", "kind", "stage", "message", "created_at")
    list_filter = ("kind", "stage")
    search_fields = ("message",)
    raw_id_fields = ("bundle",)
    readonly_fields = ("kind", "stage", "message", "detail", "created_at")
    date_hierarchy = "created_at"


@admin.register(MigrationConflict, site=platform_admin_site)
class MigrationConflictAdmin(admin.ModelAdmin):
    list_display = ("bundle", "domain", "canonical_model", "canonical_pk",
                    "legacy_id", "resolution", "resolved_by", "created_at")
    list_filter = ("resolution", "domain", "canonical_model")
    search_fields = ("legacy_id", "canonical_pk", "canonical_model")
    raw_id_fields = ("bundle", "resolved_by")
    readonly_fields = ("existing_values", "incoming_values", "changed_fields", "created_at")
    date_hierarchy = "created_at"
