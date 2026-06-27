"""
Signal handlers for audit logging: comprehensive tracking of model changes and user actions.
Phase 4: Automatically log CREATE, UPDATE, DELETE for audit trail.
"""

from decimal import Decimal
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

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
        if hasattr(value, "isoformat"):  # datetime
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)
        elif hasattr(value, "__dict__") and not isinstance(
            value, (str, int, float, bool, type(None))
        ):
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


def _current_actor_id():
    """Best-effort current-request actor PK (int) for audit attribution, or None.

    The auto CREATE/UPDATE/DELETE handlers run at the ORM layer with no handle on
    the request, so historically every model-mutation AuditLog row was written
    with ``user=None`` — the trail captured WHAT changed but never WHO. This reads
    the request-scoped contextvar populated by the observability middleware
    (``request.user.pk``) so a mutation made during a request is attributed to the
    acting user. Returns None outside a request (system / management-command /
    migration writes stay unattributed, exactly as before). Never raises —
    attribution must not break the save it is observing.
    """
    try:
        from apps.observability.logging_context import get_current_user_id

        raw = get_current_user_id()
    except Exception:  # noqa: BLE001 — attribution is best-effort, never fatal
        return None
    if raw and raw.isdigit():
        return int(raw)
    return None


def _impersonation_audit_fields() -> dict:
    """Operator-impersonation provenance for an audit row, or {} when not impersonating.

    Wave C #4 Phase 2: request.user is already the operator during impersonation
    (Phase 1 attributes the row to them), so this only adds the "during impersonation
    of school X" fact. Returns {} outside impersonation so the model defaults
    (during_impersonation=False) apply unchanged. Never raises.
    """
    try:
        from apps.observability.logging_context import (
            get_current_during_impersonation,
            get_current_impersonated_school_id,
        )

        if get_current_during_impersonation():
            return {
                "during_impersonation": True,
                "impersonated_school_id": (get_current_impersonated_school_id() or "")[:64],
            }
    except Exception:  # noqa: BLE001 — provenance is best-effort, never fatal
        return {}
    return {}


@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    """Auto-log model CREATE and UPDATE via AuditLog."""
    from apps.compliance.models_audit import AuditLog

    # Skip audit models and Django internals
    if sender.__name__ in [
        "AuditLog",
        "UserActivitySession",
        "AccessLog",
        "ComplianceReport",
    ]:
        return
    if sender.__module__.startswith("django."):
        return
    if not getattr(sender, "audit_enabled", False):
        return

    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE
    old_values, new_values, changed_fields = get_model_changes(
        sender, instance, created=created
    )

    # Classify sensitivity
    model_name = sender.__name__
    if any(
        x in model_name
        for x in ["Invoice", "Payment", "Salary", "Grade", "StudentProfile"]
    ):
        sensitivity = AuditLog.Sensitivity.CRITICAL
    elif any(x in model_name for x in ["User", "Permission", "Teacher", "Student"]):
        sensitivity = AuditLog.Sensitivity.HIGH
    else:
        sensitivity = AuditLog.Sensitivity.MEDIUM

    AuditLog.objects.create(
        user_id=_current_actor_id(),
        action=action,
        model_name=model_name,
        object_id=str(instance.pk),
        object_repr=str(instance)[:500],
        app_label=sender.__module__.split(".")[1],
        old_values=old_values,
        new_values=new_values,
        changed_fields=changed_fields,
        sensitivity=sensitivity,
        **_impersonation_audit_fields(),
    )


@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    """Auto-log model DELETE via AuditLog."""
    from apps.compliance.models_audit import AuditLog

    if sender.__name__ in [
        "AuditLog",
        "UserActivitySession",
        "AccessLog",
        "ComplianceReport",
    ]:
        return
    if sender.__module__.startswith("django."):
        return
    if not getattr(sender, "audit_enabled", False):
        return

    model_name = sender.__name__
    if any(
        x in model_name
        for x in ["Invoice", "Payment", "Salary", "Grade", "StudentProfile"]
    ):
        sensitivity = AuditLog.Sensitivity.CRITICAL
    elif any(x in model_name for x in ["User", "Permission", "Teacher", "Student"]):
        sensitivity = AuditLog.Sensitivity.HIGH
    else:
        sensitivity = AuditLog.Sensitivity.MEDIUM

    AuditLog.objects.create(
        user_id=_current_actor_id(),
        action=AuditLog.Action.DELETE,
        model_name=model_name,
        object_id=str(instance.pk),
        object_repr=str(instance)[:500],
        app_label=sender.__module__.split(".")[1],
        old_values=_serialize_instance(instance),
        sensitivity=sensitivity,
        **_impersonation_audit_fields(),
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
    except (ImportError, AttributeError, TypeError, ValueError):
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
    except (ValueError, TypeError, AttributeError, ConnectionError, OSError):
        try:
            from apps.siteconfig.cache_utils import get_tenant_cache_prefix

            prefix = get_tenant_cache_prefix()
            cache.set(f"{prefix}:access_rules_version", 1, None)
        except (ValueError, TypeError, AttributeError, ConnectionError, OSError):
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


# ---------------------------------------------------------------------------
# Authentication audit signals (SOC 2 CC6 / CC7, ISO 27001 A.12.4, FERPA access log).
# Without these, AuditLog.Action.LOGIN / LOGOUT / ACCESS_DENIED enum values are
# never written and the audit-log UI's "Recent logins" view is silent.
# ---------------------------------------------------------------------------

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)


def _client_ip(request) -> str | None:
    """Best-effort client IP extraction honoring X-Forwarded-For."""
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "") if hasattr(request, "META") else ""
    if xff:
        return xff.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") if hasattr(request, "META") else None


def _client_user_agent(request) -> str:
    if request is None or not hasattr(request, "META"):
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:500]


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Audit successful login. SOC 2 CC6.1 logical access tracking."""
    try:
        AuditLog.objects.create(
            user=user,
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            action=AuditLog.Action.LOGIN,
            model_name="User",
            object_id=str(getattr(user, "pk", "")),
            object_repr=(getattr(user, "get_username", lambda: "")() or "")[:500],
            app_label="accounts",
            sensitivity=AuditLog.Sensitivity.HIGH,
            new_values={
                "mfa_verified": bool(getattr(user, "is_verified", lambda: False)())
                if hasattr(user, "is_verified")
                else None,
            },
        )
    except (ValueError, TypeError, AttributeError):
        # Never block login on audit-write failure.
        pass


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Audit explicit logout."""
    if user is None:
        return
    try:
        AuditLog.objects.create(
            user=user,
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            action=AuditLog.Action.LOGOUT,
            model_name="User",
            object_id=str(getattr(user, "pk", "")),
            object_repr=(getattr(user, "get_username", lambda: "")() or "")[:500],
            app_label="accounts",
            sensitivity=AuditLog.Sensitivity.MEDIUM,
        )
    except (ValueError, TypeError, AttributeError):
        pass


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request=None, **kwargs):
    """Audit failed login. ACCESS_DENIED is the closest semantic for SOC 2 brute-force evidence."""
    try:
        attempted_username = ""
        if isinstance(credentials, dict):
            attempted_username = (
                credentials.get("username")
                or credentials.get("email")
                or credentials.get("login")
                or ""
            )
        AuditLog.objects.create(
            user=None,
            ip_address=_client_ip(request),
            user_agent=_client_user_agent(request),
            action=AuditLog.Action.ACCESS_DENIED,
            model_name="User",
            object_id="",
            object_repr=str(attempted_username)[:500],
            app_label="accounts",
            sensitivity=AuditLog.Sensitivity.HIGH,
            reason="Failed login attempt",
        )
    except (ValueError, TypeError, AttributeError):
        pass
