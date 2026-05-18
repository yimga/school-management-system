"""DRF serializers for the Migration Cloud public REST API alpha.

Every serializer enumerates ``Meta.fields`` explicitly — no ``__all__``,
per project convention (predictable surface area; new fields are opt-in
to the API rather than auto-exposed).

Read/write split:
    MigrationBundle — server-owned status fields (status, summaries) are
    read-only; intake fields (source_hint, intake_method, label, school)
    are write-on-create-only.

    MigrationArtifact — id / bundle / filename / path / profile are
    read-only after creation; artifacts are produced by the ingestion
    pipeline, not by API callers.

    MigrationRun — fully read-only; runs are produced by the orchestrator
    during apply.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.migration_cloud.models import (
    MigrationArtifact,
    MigrationBundle,
)


class MigrationBundleSerializer(serializers.ModelSerializer):
    """Public-API view of a MigrationBundle.

    Status + summary fields are read-only — they advance via the wizard
    state machine, not direct PATCH. Intake fields are write-on-create
    so partners can POST a bundle skeleton and then attach artifacts /
    advance stages via the dedicated action endpoints.
    """

    school_id = serializers.IntegerField(
        source="school.pk",
        read_only=True,
        allow_null=True,
        help_text="Target tenant FK; null for pre-tenant staging bundles.",
    )

    class Meta:
        model = MigrationBundle
        fields = [
            "id",
            "school_id",
            "label",
            "source_hint",
            "intake_method",
            "status",
            "sla_tier",
            "size_summary",
            "discovery_summary",
            "mapping_summary",
            "reconciliation_summary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "size_summary",
            "discovery_summary",
            "mapping_summary",
            "reconciliation_summary",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "source_hint": {"required": False, "allow_blank": True},
            "intake_method": {"required": False},
            "label": {"required": False, "allow_blank": True},
            "sla_tier": {"required": False},
        }


class MigrationArtifactSerializer(serializers.ModelSerializer):
    """Public-API view of a MigrationArtifact (one file/sheet inside a bundle)."""

    bundle_id = serializers.IntegerField(source="bundle.pk", read_only=True)

    class Meta:
        model = MigrationArtifact
        fields = [
            "id",
            "bundle_id",
            "filename",
            "path_within_bundle",
            "detected_format",
            "byte_size",
            "row_count",
            "column_count",
            "profile",
            "quarantined",
            "created_at",
        ]
        read_only_fields = fields  # artifacts come from the ingestion pipeline


class MigrationRunSerializer(serializers.Serializer):
    """Public-API view of one MigrationRun row from the apply step.

    ``MigrationRun`` lives in ``apps.automation`` (see models.py docstring),
    so we don't ModelSerialize against it from here — we project the fields
    we need with a plain Serializer so we don't take a hard import-time
    dependency on automation's model surface.
    """

    id = serializers.IntegerField(read_only=True)
    bundle_id = serializers.IntegerField(read_only=True)
    stage = serializers.CharField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_count = serializers.IntegerField(read_only=True, default=0)
    updated_count = serializers.IntegerField(read_only=True, default=0)
    quarantined_count = serializers.IntegerField(read_only=True, default=0)
