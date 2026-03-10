"""
Record MetadataChangeLog when policy metadata is saved (metadata plan todo 6).
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import BlueprintPack, PolicyBundle


@receiver(post_save, sender=PolicyBundle)
def log_policy_bundle_save(sender, instance, created, **kwargs):
    try:
        from apps.metadata.changelog import record_metadata_changelog
        scope = "tenant"
        record_metadata_changelog(
            object_type="PolicyBundle",
            object_id=str(instance.pk),
            scope=scope,
            new_value_summary={"name": instance.name, "school_id": str(instance.school_id) if instance.school_id else None},
            reason="created" if created else "updated",
        )
    except Exception:
        pass


@receiver(post_save, sender=BlueprintPack)
def log_blueprint_pack_save(sender, instance, created, **kwargs):
    try:
        from apps.metadata.changelog import record_metadata_changelog
        record_metadata_changelog(
            object_type="BlueprintPack",
            object_id=str(instance.pk),
            scope="platform",
            new_value_summary={"slug": instance.slug, "name": instance.name},
            reason="created" if created else "updated",
        )
    except Exception:
        pass
