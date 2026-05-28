"""v4.00.13 — Platform-runtime DRF permission classes.

Closes the v4.00.12 follow-on gap: the JIT operator controller existed but
no permission class actually used it. This module ships the integration
point — DRF views set ``permission_classes = [IsJITAuthorizedOperator]``
and the controller's ``check_jit_authorization`` gate runs on every request.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class IsJITAuthorizedOperator:
    """DRF permission: pass only when the request user has a live JIT grant on the request tenant.

    The check looks at ``request.tenant.settings["operator_access"]["jit_grants"]``
    (or ``request.school.settings`` — both common attr names are supported) and
    matches the user id against the grant list.

    Returns 403 when:
    * the user is anonymous,
    * there is no tenant/school on the request,
    * the user has no live grant.

    The view's caller can read ``request.jit_grant`` after this permission
    passes to get the ``JITGrant`` dataclass for downstream gdpr_resolver +
    apply_regional_mask composition.

    Duck-typed to DRF's BasePermission contract — does NOT import rest_framework
    so apps that don't use DRF can still import this module.
    """

    message = "JIT operator authorization required."

    def has_permission(self, request: Any, view: Any) -> bool:  # noqa: ARG002
        from apps.platform_runtime.jit_operator_controller import check_jit_authorization

        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        operator_user_id = getattr(user, "pk", None)
        if operator_user_id is None:
            return False

        tenant = getattr(request, "tenant", None) or getattr(request, "school", None)
        if tenant is None:
            return False
        settings = getattr(tenant, "settings", None)
        if not isinstance(settings, dict):
            return False

        grant = check_jit_authorization(
            operator_user_id=int(operator_user_id),
            school_settings=settings,
        )
        # Make the grant available on the request for downstream code paths
        # (gdpr_resolver, apply_regional_mask) without re-running the check.
        try:
            request.jit_grant = grant  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        if grant.granted:
            return True
        # Surface the reason in the message so the 403 body explains the gate.
        self.message = f"JIT operator authorization required ({grant.reason})."
        logger.info(
            "IsJITAuthorizedOperator: denied operator_user_id=%s reason=%s",
            operator_user_id, grant.reason,
        )
        return False

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:  # noqa: ARG002
        # Per-object check piggybacks on the request-level check; if the
        # request passed has_permission, the object is also visible (subject
        # to gdpr_resolver / apply_regional_mask in the serializer layer).
        return self.has_permission(request, view)
