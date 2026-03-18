"""
Signals to record MetadataChangeLog when metadata models are saved (metadata plan todo 6).
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .changelog import record_metadata_changelog
from .models import EntityCatalogEntry, FieldCatalogEntry, LayoutDefinition


def _summarize(instance, fields: list) -> dict:
    out = {}
    for f in fields:
        if hasattr(instance, f):
            out[f] = getattr(instance, f)
    return out


@receiver(post_save, sender=EntityCatalogEntry)
def log_entity_catalog_save(sender, instance, created, **kwargs):
    scope = (
        getattr(instance, "scope", "platform")
        if hasattr(instance, "scope")
        else "platform"
    )
    record_metadata_changelog(
        object_type="EntityCatalogEntry",
        object_id=str(instance.pk),
        scope=scope,
        new_value_summary={"code": instance.code, "name": instance.name},
        reason="created" if created else "updated",
    )


@receiver(post_save, sender=FieldCatalogEntry)
def log_field_catalog_save(sender, instance, created, **kwargs):
    record_metadata_changelog(
        object_type="FieldCatalogEntry",
        object_id=str(instance.pk),
        scope="platform",
        new_value_summary={
            "entity_id": instance.entity_id,
            "field_name": instance.field_name,
        },
        reason="created" if created else "updated",
    )


@receiver(post_save, sender=LayoutDefinition)
def log_layout_definition_save(sender, instance, created, **kwargs):
    scope = getattr(instance, "scope", "tenant")
    record_metadata_changelog(
        object_type="LayoutDefinition",
        object_id=str(instance.pk),
        scope=scope,
        new_value_summary={"code": instance.code, "scope": scope},
        reason="created" if created else "updated",
    )
