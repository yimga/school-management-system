"""v4.00.14 — Operator tenant inspector DRF view.

Closes the v4.00.13 follow-on opportunity: ``IsJITAuthorizedOperator`` existed
but no DRF view used it. This module wires the permission into a concrete
operator surface — ``/api/v1/super/tenant-inspect/<int:school_id>/`` — that
returns operator-safe tenant metadata composed through the full JIT + GDPR
resolver + regional mask chain.

Operators MUST have a live JIT grant on the target tenant before the view
returns any record. Forbidden fields are dropped; regionally-masked fields
are redacted character-by-character. The view never persists anything.
"""

from __future__ import annotations

import logging

from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views import View

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
class OperatorTenantInspectView(View):
    """GET /api/v1/super/tenant-inspect/<int:school_id>/

    # rbac-allow: super-staff-operator-tenant-inspect-jit-gated
    """

    permission_classes = ("apps.platform_runtime.permissions.IsJITAuthorizedOperator",)

    def get(self, request: HttpRequest, school_id: int) -> JsonResponse:
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "authentication_required"}, status=401)

        from apps.platform_runtime.jit_operator_controller import compose_operator_view
        from apps.platform_runtime.permissions import IsJITAuthorizedOperator

        try:
            from apps.schools.models import School
        except ImportError:
            return JsonResponse({"error": "schools_unavailable"}, status=503)

        # tenant-isolation-allow: explicit-pk-lookup-operator-jit-gated-inspect
        school = School.objects.filter(pk=int(school_id)).first()
        if school is None:
            return JsonResponse({"error": "tenant_not_found"}, status=404)

        # Bind the resolved tenant onto the request so the permission class
        # reads the right settings dict; supports both attribute names.
        try:
            request.tenant = school  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

        permission = IsJITAuthorizedOperator()
        if not permission.has_permission(request, self):
            return JsonResponse({"error": "jit_denied", "reason": permission.message}, status=403)

        record = {
            "id": school.pk,
            "name": getattr(school, "name", "") or "",
            "slug": getattr(school, "slug", "") or "",
            "subdomain": getattr(school, "subdomain", "") or "",
            "country_code": getattr(school, "country_code", "") or "",
            "primary_sector": getattr(school, "primary_sector", "") or "",
            "is_active": bool(getattr(school, "is_active", False)),
            "is_approved": bool(getattr(school, "is_approved", False)),
            "last_activity": (
                getattr(school, "last_activity", None).isoformat()
                if getattr(school, "last_activity", None) is not None
                else None
            ),
            # Operator-relevant administrative contact (mask candidates).
            "contact_email": getattr(school, "contact_email", "") or "",
            "phone": getattr(school, "phone", "") or "",
            "full_name": getattr(school, "principal_full_name", "") or "",
        }

        region = (
            getattr(school, "country_code", "")
            or getattr(school, "region_code", "")
            or ""
        )
        grant, visible = compose_operator_view(
            operator_user_id=int(getattr(request.user, "pk", 0) or 0),
            school_settings=getattr(school, "settings", None) or {},
            region=region or None,
            record=record,
        )

        return JsonResponse({
            "school_id": school.pk,
            "region": region,
            "jit_grant": {
                "granted": grant.granted,
                "expires_at_iso": grant.expires_at_iso,
                "reason": grant.reason,
            },
            "record": visible,
        })
