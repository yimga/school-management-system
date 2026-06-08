import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

import apps.siteconfig.models as _siteconfig_models
from .models import TenantSystem, ThemePack

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")

logger = logging.getLogger("siteconfig.audit")
SIGNAL_SOFT_FAILURES = (
    AttributeError,
    ImportError,
    LookupError,
    RuntimeError,
    TypeError,
    ValueError,
)

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
        except (AttributeError, TypeError, ValueError):
            continue
        if old_val != new_val:
            changes[fname] = (old_val, new_val)
    return changes


@receiver(pre_save, sender=_TenantSettingsModel)
def log_site_settings_change(sender, instance, **kwargs):
    changes = get_changed_fields(instance)
    if changes:
        logger.info(f"Tenant platform settings row changed: {changes}")


@receiver(pre_save, sender=ThemePack)
def log_theme_pack_change(sender, instance, **kwargs):
    changes = get_changed_fields(instance)
    if changes:
        logger.info(f"ThemePack changed: {changes}")


@receiver(post_save, sender=_TenantSettingsModel)
@receiver(post_delete, sender=_TenantSettingsModel)
@receiver(post_save, sender=ThemePack)
@receiver(post_delete, sender=ThemePack)
def invalidate_effective_site_settings_runtime_cache(sender, instance, **kwargs):
    try:
        from apps.platform_runtime.helpers import (
            invalidate_effective_site_settings_cache,
        )

        invalidate_effective_site_settings_cache()
    except SIGNAL_SOFT_FAILURES as exc:
        logger.debug("invalidate_effective_site_settings_cache: %s", exc)


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
    except SIGNAL_SOFT_FAILURES as e:
        logger.debug(
            "sync_tenant_modules_to_school_features after TenantSystem change: %s", e
        )


# Route workflow/dashboard pack assignment through the canonical PackageEngine.
def _on_workflow_pack_assignment_save(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        pack = getattr(instance, "workflow_pack", None)
        if not pack:
            return
        from apps.packages.engine import PackageEngine

        school_id = getattr(instance, "school_id", None)
        PackageEngine.apply_package(
            tenant_id=school_id,
            package_id=getattr(pack, "code", "") or str(pack.pk),
            version=getattr(pack, "version", "1") or "1",
            payload_sections={
                "workflow": {"module_slug": getattr(instance, "module_slug", "")}
            },
            mode="production",
        )
    except SIGNAL_SOFT_FAILURES as e:
        logger.debug("PackageEngine after WorkflowPackAssignment: %s", e)


def _on_dashboard_pack_assignment_save(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        pack = getattr(instance, "dashboard_pack", None)
        if not pack:
            return
        from apps.packages.engine import PackageEngine

        school_id = getattr(instance, "school_id", None)
        PackageEngine.apply_package(
            tenant_id=school_id,
            package_id=getattr(pack, "code", "") or str(pack.pk),
            version=getattr(pack, "version", "1") or "1",
            payload_sections={"dashboard": {"role": getattr(instance, "role", "")}},
            mode="production",
        )
    except SIGNAL_SOFT_FAILURES as e:
        logger.debug("PackageEngine after DashboardPackAssignment: %s", e)


def _connect_pack_assignment_signals():
    try:
        from .models_workflow import WorkflowPackAssignment
        from .models_dashboard import DashboardPackAssignment

        post_save.connect(
            _on_workflow_pack_assignment_save, sender=WorkflowPackAssignment, weak=False
        )
        post_save.connect(
            _on_dashboard_pack_assignment_save,
            sender=DashboardPackAssignment,
            weak=False,
        )
    except (AttributeError, ImportError, RuntimeError):
        pass
