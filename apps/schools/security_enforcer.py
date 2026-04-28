"""
Tenant security decorators — fail closed; require membership + coarse action (SLICE 10+).

Uses ``has_school_permission`` from ``tenant_access``; superusers pass with school context when present.

**MFA / support / impersonation:** Multi-factor and step-up authentication are enforced at login
and session policy layers (accounts middleware), not in these decorators. Platform impersonation
and dual-control approval live under ``apps/schools/super_views_impersonation`` (``switch_to_tenant``)
and ``docs/compliance/MFA_SUPPORT_ACCESS.md``. Control-plane vs tenant separation is enforced by
``apps/schools/control_plane.require_super_access_with_host`` and ``user_has_control_plane_access``.

**Export audit hook:** Use ``best_effort_audit_export_download`` from downloadable responses when
adding new tenant-scoped exports so compliance receives a consistent ``AuditLog`` trail.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional

from django.http import HttpRequest, HttpResponseForbidden

from apps.schools.tenant_access import SchoolAction, has_school_permission


def enforce_tenant_security(
    view_func: Optional[Callable] = None,
    *,
    action: SchoolAction = "view",
    require_school: bool = True,
):
    """
    Decorator: ``request.user`` authenticated; ``request.school`` optional/required;
    ``has_school_permission(user, school, action)``.
    """

    def _decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def _inner(request: HttpRequest, *args, **kwargs):
            u = request.user
            if not u.is_authenticated:
                return HttpResponseForbidden("Authentication required")
            school = getattr(request, "school", None)
            if require_school and school is None:
                return HttpResponseForbidden("No school context for this request")
            if school is not None and not has_school_permission(u, school, action):
                return HttpResponseForbidden(
                    "Not permitted for this school or not a member."
                )
            return fn(request, *args, **kwargs)

        return _inner

    if view_func is not None and callable(view_func):
        return _decorator(view_func)
    return _decorator


def require_school_permission(action: SchoolAction):
    """Partial: ``@require_school_permission("export")`` etc."""
    return enforce_tenant_security(action=action, require_school=True)


require_export_permission = require_school_permission("export")
require_admin_permission = require_school_permission("admin")


def best_effort_audit_export_download(
    request: HttpRequest,
    *,
    export_key: str,
    school=None,
    academic_year_id: int | None = None,
    app_label: str = "exports",
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Record an EXPORT row in ``AuditLog`` when compliance models are available.

    Safe no-op on failure (missing migrations, DB errors). Mirrors the pattern used in
    ``siteconfig.views_compliance_exports`` so operators get a single audit trail shape.
    """
    school = school if school is not None else getattr(request, "school", None)
    try:
        from apps.compliance.models_audit import AuditLog

        payload = {
            "export_key": export_key,
            "school_id": str(getattr(school, "pk", "") or ""),
            "academic_year_id": academic_year_id,
        }
        if extra:
            payload.update(extra)
        AuditLog.objects.create(
            action=AuditLog.Action.EXPORT,
            user=request.user if getattr(request.user, "is_authenticated", False) else None,
            model_name="TenantExport",
            object_id=str(
                f"{export_key}:{getattr(school, 'pk', '')}:{academic_year_id or ''}"
            )[:200],
            object_repr=f"export {export_key}",
            app_label=app_label,
            new_values=payload,
        )
    except Exception:
        return
