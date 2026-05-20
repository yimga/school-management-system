"""Field mapping suggestions and confirmation."""

from __future__ import annotations

from decimal import Decimal

from apps.migration_cloud.models_connectors import (
    FieldMappingStatus,
    MigrationFieldMapping,
    MigrationSourceConnection,
)
from apps.migration_cloud.services.connector_audit import record_connector_audit
from apps.platform_runtime import migration_center


def suggest_field_mappings(
    *,
    connection: MigrationSourceConnection,
    entity_type: str,
    source_fields: list[str],
    actor=None,
) -> list[MigrationFieldMapping]:
    if entity_type not in migration_center.MIGRATION_TEMPLATES:
        entity_type = "students"
    suggestions = migration_center.build_field_mapping(source_fields, entity=entity_type)
    created: list[MigrationFieldMapping] = []
    for row in suggestions:
        dest = row.get("destination_field") or ""
        confidence = Decimal("90.00") if dest else Decimal("40.00")
        mapping, _ = MigrationFieldMapping.objects.update_or_create(
            source_connection=connection,
            source_entity=entity_type,
            source_field=row["source_field"],
            defaults={
                "school": connection.school,
                "destination_model": entity_type,
                "destination_field": dest,
                "transform_rule": row.get("transformation", ""),
                "required": row.get("required", "false") == "true",
                "confidence": confidence,
                "status": (
                    FieldMappingStatus.SUGGESTED
                    if dest
                    else FieldMappingStatus.NEEDS_REVIEW
                ),
            },
        )
        created.append(mapping)
    return created


def confirm_mappings(
    *,
    connection: MigrationSourceConnection,
    entity_type: str,
    actor,
) -> int:
    updated = MigrationFieldMapping.objects.filter(
        school=connection.school,
        source_connection=connection,
        source_entity=entity_type,
    ).exclude(status=FieldMappingStatus.IGNORED).update(
        status=FieldMappingStatus.CONFIRMED
    )
    record_connector_audit(
        school=connection.school,
        actor=actor,
        event_type="mapping_confirmed",
        source_connection=connection,
        metadata={"entity_type": entity_type, "count": updated},
    )
    return updated


def required_fields_blocked(connection: MigrationSourceConnection, entity_type: str) -> list[str]:
    """Return destination required fields still unmapped."""
    template = migration_center.MIGRATION_TEMPLATES.get(entity_type, {})
    required = set(template.get("required", []))
    mapped = set(
        MigrationFieldMapping.objects.filter(
            school=connection.school,
            source_connection=connection,
            source_entity=entity_type,
            status__in=[FieldMappingStatus.CONFIRMED, FieldMappingStatus.SUGGESTED],
        )
        .exclude(destination_field="")
        .values_list("destination_field", flat=True)
    )
    return sorted(required - mapped)
