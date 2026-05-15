"""Unfold admin registration for Migration Cloud (Phase U1).

Operator-only surfaces; the rich wizard ships in Phase U6. These admin pages
are the minimum viable inspection surface until the bespoke control-plane
template lands.
"""

from __future__ import annotations

from django.contrib import admin
from config.admin import platform_admin_site

from .models import MigrationArtifact, MigrationBundle


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
