"""
Signal handlers for audit logging: comprehensive tracking of model changes and user actions.
Phase 4: Automatically log CREATE, UPDATE, DELETE for audit trail.
"""

from decimal import Decimal
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.compliance.models_audit import AuditLog


def get_model_changes(sender, instance, created=False, **kwargs):
    """
    Extract changes from a model instance for audit logging.
    Returns: (old_values, new_values, changed_fields)
    """
    if created:
        return None, _serialize_instance(instance), None
    
    try:
        old_instance = sender.objects.get(pk=instance.pk)
        old_values = _serialize_instance(old_instance)
        new_values = _serialize_instance(instance)
        changed_fields = _get_changed_fields(old_values, new_values)
        return old_values, new_values, changed_fields
    except sender.DoesNotExist:
        return None, _serialize_instance(instance), None


def _serialize_instance(instance):
    """Serialize model instance to JSON-safe dict."""
    data = {}
    for field in instance._meta.fields:
        value = getattr(instance, field.name)
        if hasattr(value, 'isoformat'):  # datetime
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)
        elif hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool, type(None))):
            value = str(value)
        data[field.name] = value
    return data


def _get_changed_fields(old_values, new_values):
    """Return list of field names that changed."""
    if not old_values or not new_values:
        return None
    changed = []
    for key in new_values:
        if old_values.get(key) != new_values.get(key):
            changed.append(key)
    return changed or None


@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    """Auto-log model CREATE and UPDATE via AuditLog."""
    from apps.compliance.models_audit import AuditLog
    
    # Skip audit models and Django internals
    if sender.__name__ in ['AuditLog', 'UserActivitySession', 'AccessLog', 'ComplianceReport']:
        return
    if sender.__module__.startswith('django.'):
        return
    if not getattr(sender, 'audit_enabled', False):
        return
    
    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE
    old_values, new_values, changed_fields = get_model_changes(sender, instance, created=created)
    
    # Classify sensitivity
    model_name = sender.__name__
    if any(x in model_name for x in ['Invoice', 'Payment', 'Salary', 'Grade', 'StudentProfile']):
        sensitivity = AuditLog.Sensitivity.CRITICAL
    elif any(x in model_name for x in ['User', 'Permission', 'Teacher', 'Student']):
        sensitivity = AuditLog.Sensitivity.HIGH
    else:
        sensitivity = AuditLog.Sensitivity.MEDIUM
    
    AuditLog.objects.create(
        action=action,
        model_name=model_name,
        object_id=str(instance.pk),
        object_repr=str(instance)[:500],
        app_label=sender.__module__.split('.')[1],
        old_values=old_values,
        new_values=new_values,
        changed_fields=changed_fields,
        sensitivity=sensitivity,
    )


@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    """Auto-log model DELETE via AuditLog."""
    from apps.compliance.models_audit import AuditLog
    
    if sender.__name__ in ['AuditLog', 'UserActivitySession', 'AccessLog', 'ComplianceReport']:
        return
    if sender.__module__.startswith('django.'):
        return
    if not getattr(sender, 'audit_enabled', False):
        return
    
    model_name = sender.__name__
    if any(x in model_name for x in ['Invoice', 'Payment', 'Salary', 'Grade', 'StudentProfile']):
        sensitivity = AuditLog.Sensitivity.CRITICAL
    elif any(x in model_name for x in ['User', 'Permission', 'Teacher', 'Student']):
        sensitivity = AuditLog.Sensitivity.HIGH
    else:
        sensitivity = AuditLog.Sensitivity.MEDIUM
    
    AuditLog.objects.create(
        action=AuditLog.Action.DELETE,
        model_name=model_name,
        object_id=str(instance.pk),
        object_repr=str(instance)[:500],
        app_label=sender.__module__.split('.')[1],
        old_values=_serialize_instance(instance),
        sensitivity=sensitivity,
    )


@receiver(post_save, sender=AuditLog)
def alert_on_critical_audit(sender, instance: AuditLog, created, **kwargs):
    """Trigger real-time alerts for critical/high-sensitivity audit events."""
    if not created:
        return

    # Avoid alert loops if alerts are disabled
    from django.conf import settings
    if not getattr(settings, "COMPLIANCE_ALERTS", {}).get("enabled", True):
        return

    try:
        from apps.compliance.alerts import notify_audit_event

        notify_audit_event(instance)
    except Exception:
        # Swallow to keep request flow unaffected
        pass


# Invalidate cached access checks whenever access rules change by bumping a version
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete


def _bump_rules_version():
    """Increment a cached version key used by access control cache keys (tenant-scoped)."""
    try:
        from apps.siteconfig.cache_utils import get_tenant_cache_prefix
        prefix = get_tenant_cache_prefix()
        key = f"{prefix}:access_rules_version"
        cache.incr(key)
    except Exception:
        try:
            from apps.siteconfig.cache_utils import get_tenant_cache_prefix
            prefix = get_tenant_cache_prefix()
            cache.set(f"{prefix}:access_rules_version", 1, None)
        except Exception:
            pass


@receiver(post_save, sender=None)
def _noop_for_receiver(*_, **__):
    # placeholder to allow multiple receiver decorators below
    pass


# Attach explicit handlers for IPAccessRule and CountryAccessRule
from apps.compliance.models_audit import IPAccessRule, CountryAccessRule


@receiver(post_save, sender=IPAccessRule)
@receiver(post_delete, sender=IPAccessRule)
@receiver(post_save, sender=CountryAccessRule)
@receiver(post_delete, sender=CountryAccessRule)
def refresh_access_rules_cache(sender, instance, **kwargs):
    """Called when an access rule is created/updated/deleted to invalidate cached checks."""
    _bump_rules_version()
