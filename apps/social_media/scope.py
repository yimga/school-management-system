"""Tenant scope enforcement for social media operations."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied
from rest_framework import status
from rest_framework.response import Response

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.schools.models import School
    from apps.social_media.models import SocialMediaIntegration

logger = logging.getLogger(__name__)


class SocialTenantScopeError(PermissionDenied):
    """Raised when a caller attempts cross-tenant social access."""


def integration_scope_key(integration: SocialMediaIntegration) -> str:
    if integration.school_id:
        return f"tenant:{integration.school_id}"
    return "platform"


def resolve_feed_scope(request: HttpRequest) -> tuple[School | None, bool]:
    """
    Return (school, is_platform_scope).

    Platform marketing / manager host without tenant → platform scope (school=None).
    Tenant host with request.school → tenant scope.
    """
    school = getattr(request, "school", None)
    if school is not None:
        return school, False
    host = (getattr(request, "get_host", lambda: "")() or "").lower()
    if host.startswith("manager.") or host in ("runmycampus.com", "www.runmycampus.com"):
        return None, True
    return None, False


def queryset_for_scope(
    model_manager,
    *,
    school: School | None,
    platform_scope: bool,
):
    """Turn a resolved scope into a queryset, fail-closed on the ambiguous case.

    The three arms are NOT interchangeable: "platform" means ``school__isnull=True``
    (the corporate accounts), a tenant means ``school=``, and "no school and no
    affirmative platform host" means ``.none()`` -- never an unfiltered queryset.
    This helper had zero callers and was catalogued as dead code while
    ``publisher.enqueue_cross_post`` open-coded the same decision and got the third
    arm backwards, reading "no school" as "platform". It is the caller now.
    """
    if platform_scope:
        return model_manager.filter(school__isnull=True)
    if school is None:
        return model_manager.none()
    return model_manager.filter(school=school)


def assert_integration_access(
    request: HttpRequest,
    integration: SocialMediaIntegration,
    *,
    action: str = "read",
) -> None:
    school = getattr(request, "school", None)
    if integration.school_id is None:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise SocialTenantScopeError("Authentication required for platform social scope.")
        # ``is_staff`` is NOT an operator marker on this platform: the default
        # tenant admin is created with is_staff=True
        # (accounts/management/commands/ensure_default_tenant_admin.py), so the
        # old test admitted every school's ADMIN to the COMPANY's own social
        # credentials. ``user_has_control_plane_access`` is the platform's real
        # operator predicate -- superuser, or an active PlatformOperatorProfile,
        # or an operator role with no SchoolMembership -- and it deliberately
        # excludes tenant staff.
        from apps.schools.control_plane import user_has_control_plane_access

        if not user_has_control_plane_access(user):
            logger.critical(
                "social_cross_scope_blocked",
                extra={
                    "action": action,
                    "integration_id": str(integration.id),
                    "reason": "platform_integration_non_operator",
                },
            )
            raise SocialTenantScopeError(
                "Platform social credentials require platform-operator access."
            )
        return

    if school is None or integration.school_id != school.id:
        logger.critical(
            "social_cross_scope_blocked",
            extra={
                "action": action,
                "integration_id": str(integration.id),
                "requested_school": str(getattr(school, "id", None)),
                "integration_school": str(integration.school_id),
            },
        )
        raise SocialTenantScopeError("Cross-tenant social integration access denied.")


def assert_target_school_access(request: HttpRequest, target_school_id: uuid.UUID) -> None:
    school = getattr(request, "school", None)
    if school is None or school.id != target_school_id:
        logger.critical(
            "social_cross_scope_blocked",
            extra={
                "action": "school_target",
                "requested_school": str(getattr(school, "id", None)),
                "target_school": str(target_school_id),
            },
        )
        raise SocialTenantScopeError("Cross-tenant school scope denied.")


def scope_denied_response(exc: SocialTenantScopeError) -> Response:
    return Response(
        {"error": "access_denied", "detail": str(exc)},
        status=status.HTTP_403_FORBIDDEN,
    )
