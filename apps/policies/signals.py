"""
Record MetadataChangeLog when policy metadata is saved (metadata plan todo 6).
"""
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.platform_runtime.structured_logging import log_exception_with_context

from .models import BlueprintPack, PolicyBundle

# Typed exceptions for §2.4 broad-except replacement (allowlist 0).
_POLICY_SIGNAL_CHANGELOG_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    DatabaseError,
    IntegrityError,
    ValidationError,
)


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
    except _POLICY_SIGNAL_CHANGELOG_ERRORS:
        log_exception_with_context(
            "log_policy_bundle_save: record_metadata_changelog failed",
            school_id=getattr(instance, "school_id", None),
            extra={"object_type": "PolicyBundle", "object_id": str(getattr(instance, "pk", None))},
        )


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
    except _POLICY_SIGNAL_CHANGELOG_ERRORS:
        log_exception_with_context(
            "log_blueprint_pack_save: record_metadata_changelog failed",
            school_id=None,
            extra={"object_type": "BlueprintPack", "object_id": str(getattr(instance, "pk", None))},
        )
