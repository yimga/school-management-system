"""
Wind-down commerce and enrollment guards.

Blocks mutating finance and roster writes while a tenant is in wind-down mode.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Optional

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils.translation import gettext as _

from apps.lifecycle.tenant_school_resolve import resolve_request_school
from apps.lifecycle.wind_down import is_wind_down_mode, wind_down_blocks_new_commerce


def school_from_request(request: HttpRequest):
    return resolve_request_school(request)


def wind_down_block_response(
    request: HttpRequest,
    *,
    message: Optional[str] = None,
) -> HttpResponse:
    msg = message or _(
        "This school is in wind-down mode. New enrollments and billing charges are "
        "paused. Export data or contact platform support."
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or (
        request.content_type or ""
    ).startswith("application/json"):
        return JsonResponse({"ok": False, "error": "wind_down_mode", "message": msg}, status=403)
    if request.method == "GET":
        return HttpResponseForbidden(msg)
    try:
        if hasattr(request, "_messages"):
            messages.error(request, msg)
    except Exception:
        pass
    return HttpResponseForbidden(msg)


def block_if_wind_down_commerce(request: HttpRequest) -> Optional[HttpResponse]:
    """Return a 403 response when commerce/enrollment must be blocked."""
    school = school_from_request(request)
    if school is None:
        return None
    if wind_down_blocks_new_commerce(school) or is_wind_down_mode(school):
        return wind_down_block_response(request)
    return None


def require_commerce_allowed(view_func: Callable) -> Callable:
    """Decorator: block POST (and mutating methods) during wind-down."""

    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            blocked = block_if_wind_down_commerce(request)
            if blocked is not None:
                return blocked
        return view_func(request, *args, **kwargs)

    return _wrapped


def wind_down_drf_block(request):
    """DRF-friendly 403 when wind-down blocks commerce."""
    school = school_from_request(request)
    if school is None:
        return None
    if not (wind_down_blocks_new_commerce(school) or is_wind_down_mode(school)):
        return None
    from rest_framework import status
    from rest_framework.response import Response

    msg = _(
        "School is in wind-down mode; new billing and enrollments are paused."
    )
    return Response(
        {"error": "wind_down_mode", "message": msg},
        status=status.HTTP_403_FORBIDDEN,
    )


def redirect_after_operator_school_create(request, school):
    """
    After operator rapid/API create: link to tenant provisioning + School Studio.
    When the request is already on the tenant host for this school, redirect there.
    """
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.urls import reverse

    from apps.schools.tenant_url import is_base_domain, tenant_absolute_url

    prov_url = tenant_absolute_url(
        request, "tenant_provisioning_status", school=school
    )
    studio_url = tenant_absolute_url(request, "school_studio", school=school)
    try:
        messages.success(
            request,
            _(
                "School created. Open tenant provisioning: %(prov)s — School Studio: %(studio)s"
            )
            % {"prov": prov_url, "studio": studio_url},
        )
    except Exception:
        pass
    req_school = school_from_request(request)
    if (
        not is_base_domain(request)
        and req_school is not None
        and getattr(req_school, "pk", None) == getattr(school, "pk", None)
        and prov_url
    ):
        return redirect(prov_url)
    return redirect(reverse("super:lifecycle_timeline", args=[school.id]))
