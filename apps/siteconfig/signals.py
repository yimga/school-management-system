from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from .models import SiteSettings, ThemePack, TenantSystem
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
        # Use attname (DB column) so we never load related objects; avoids queries that
        # select from related tables (e.g. finance_complianceprofile in tenant schemas
        # where that table may lack columns from newer migrations).
        attr = field.attname
        try:
            old_val = getattr(old, attr, None)
            new_val = getattr(instance, attr, None)
        except Exception:
            continue
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


# Phase A optional: sync School.features when TenantSystem is added or removed
@receiver(post_save, sender=TenantSystem)
@receiver(post_delete, sender=TenantSystem)
def sync_school_features_on_tenant_system(sender, instance, **kwargs):
    try:
        from .tenant_config import sync_tenant_modules_to_school_features
        from apps.schools.models import School
        school_id = getattr(instance, "school_id", None)
        if school_id:
            school = School.objects.filter(pk=school_id).first()
            if school:
                sync_tenant_modules_to_school_features(school, persist=True)
    except Exception as e:
        logger.debug("sync_tenant_modules_to_school_features after TenantSystem change: %s", e)
