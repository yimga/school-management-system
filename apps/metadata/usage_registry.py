"""
Register UsageReference (MetadataDependency) from workflow/dashboard/policy definitions (metadata plan todo 4).
Call register_usage() where dashboards, workflows, and policies are resolved or defined.

Lineage: use get_lineage_consumers() to answer "what uses this entity/field?" (downstream dashboards,
workflows, policies, reports) for impact preview and rollback safety.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from django.db import DatabaseError

logger = logging.getLogger(__name__)

METADATA_USAGE_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)


def register_usage(
    consumer_type: str,
    consumer_code: str,
    entity_code: str,
    field_name: str,
) -> None:
    """
    Ensure a MetadataDependency exists for consumer -> entity.field.
    Creates EntityCatalogEntry/FieldCatalogEntry if missing (minimal entries).
    """
    try:
        from apps.metadata.models import (
            EntityCatalogEntry,
            FieldCatalogEntry,
            MetadataDependency,
        )
        entity, _ = EntityCatalogEntry.objects.get_or_create(
            code=entity_code,
            defaults={"name": entity_code.replace("_", " ").title(), "description": "", "is_core": True},
        )
        field, _ = FieldCatalogEntry.objects.get_or_create(
            entity=entity,
            field_name=field_name,
            defaults={
                "label": field_name.replace("_", " ").title(),
                "data_type": "string",
                "is_custom": False,
                "source": "usage_registry",
            },
        )
        MetadataDependency.objects.get_or_create(
            consumer_type=consumer_type,
            consumer_code=consumer_code,
            field=field,
        )
    except METADATA_USAGE_SOFT_FAILURES as e:
        logger.debug("metadata register_usage skipped: %s", e)


def get_lineage_consumers(
    *,
    entity_code: str | None = None,
    field_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Lineage: which consumers (dashboards, workflows, policies, reports) use this entity or field.
    Single entry point for "what uses this?"; delegates to metadata.services.get_downstream_dependencies.
    """
    try:
        from apps.metadata.services import get_downstream_dependencies
        return get_downstream_dependencies(
            entity_code=entity_code,
            field_id=field_id,
        )
    except METADATA_USAGE_SOFT_FAILURES as e:
        logger.debug("metadata get_lineage_consumers skipped: %s", e)
        return []
