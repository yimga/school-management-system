from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import SiteSettings, ThemePack
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger("siteconfig.audit")

# Helper to get changed fields

def get_changed_fields(instance):
    if not instance.pk:
        return {}
    old = type(instance).objects.filter(pk=instance.pk).first()
    if not old:
        return {}
    changes = {}
    for field in instance._meta.fields:
        fname = field.name
        old_val = getattr(old, fname, None)
        new_val = getattr(instance, fname, None)
        if old_val != new_val:
            changes[fname] = (old_val, new_val)
    return changes

@receiver(pre_save, sender=SiteSettings)
def log_site_settings_change(sender, instance, **kwargs):
    changes = get_changed_fields(instance)
    if changes:
        logger.info(f"SiteSettings changed: {changes}")

@receiver(pre_save, sender=ThemePack)
def log_theme_pack_change(sender, instance, **kwargs):
    changes = get_changed_fields(instance)
    if changes:
        logger.info(f"ThemePack changed: {changes}")
