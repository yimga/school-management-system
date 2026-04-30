"""
Enterprise audit helpers: tenant permission changes on ``SchoolMembership`` and related
compliance ``AuditLog`` rows (no substitute for request-scoped logging where actor IP exists).

Export signing lives in ``apps.reports.export_integrity``; compliance CSV flows attach headers there.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _json_fk(val: Any) -> Any:
    """FK raw values may be UUID on some deployments; JSONField requires serializable scalars."""
    if val is None:
        return None
    return str(val)


def log_school_membership_event(
    *,
    instance,
    created: bool,
    old_role: str | None,
    deleted: bool = False,
) -> None:
    """
    Write ``AuditLog`` for membership create, role change, or delete (permission boundary).

    Actor user/IP are omitted when raised from ORM signals (migrations, shell); interactive
    requests should prefer explicit logging with request context where available.
    """
    try:
        from apps.compliance.models_audit import AuditLog

        if deleted:
            AuditLog.objects.create(
                action=AuditLog.Action.PERMISSION_REVOKE,
                user=None,
                model_name="SchoolMembership",
                object_id=str(getattr(instance, "pk", "") or ""),
                object_repr=str(instance),
                app_label="schools",
                sensitivity=AuditLog.Sensitivity.HIGH,
                old_values={
                    "role": getattr(instance, "role", ""),
                    "user_id": _json_fk(getattr(instance, "user_id", None)),
                    "school_id": _json_fk(getattr(instance, "school_id", None)),
                },
                new_values=None,
                reason="SchoolMembership removed (tenant permission revoked)",
            )
            return

        if created:
            AuditLog.objects.create(
                action=AuditLog.Action.PERMISSION_GRANT,
                user=None,
                model_name="SchoolMembership",
                object_id=str(instance.pk),
                object_repr=str(instance),
                app_label="schools",
                sensitivity=AuditLog.Sensitivity.HIGH,
                old_values=None,
                new_values={
                    "role": instance.role,
                    "user_id": _json_fk(instance.user_id),
                    "school_id": _json_fk(instance.school_id),
                },
                reason="SchoolMembership created (tenant permission granted)",
            )
            return

        if old_role is not None and old_role != instance.role:
            AuditLog.objects.create(
                action=AuditLog.Action.UPDATE,
                user=None,
                model_name="SchoolMembership",
                object_id=str(instance.pk),
                object_repr=str(instance),
                app_label="schools",
                sensitivity=AuditLog.Sensitivity.HIGH,
                old_values={"role": old_role},
                new_values={
                    "role": instance.role,
                    "user_id": _json_fk(instance.user_id),
                    "school_id": _json_fk(instance.school_id),
                },
                changed_fields=["role"],
                reason="SchoolMembership role changed (tenant permission updated)",
            )
    except Exception as exc:
        logger.debug("enterprise_audit membership log skipped: %s", exc)
