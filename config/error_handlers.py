"""
Shared Django error-page handlers for root, manager, and tenant urlconfs.

Kept in a dedicated module so ``config.manager_urls`` can import handlers without
re-entering ``config.urls`` during urlconf load (avoids circular ImportError).
"""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import get_template


def _coerce_request_user_for_error_pages(request):
    """
    Error views may run without AuthenticationMiddleware; tests may set user=None.
    Auth context processor always supplies ``user`` from request.user — ensure it is never None
    so base templates can safely reference user.username (AnonymousUser uses empty string).
    """
    from django.contrib.auth.models import AnonymousUser

    if getattr(request, "user", None) is None:
        request.user = AnonymousUser()


def permission_denied(request, exception):
    """Custom 403: friendly message when staff hit Admin without superuser."""
    _coerce_request_user_for_error_pages(request)
    is_admin_forbidden = (
        request.path.startswith("/admin")
        and request.user.is_authenticated
        and request.user.is_staff
        and not request.user.is_superuser
    )
    template = (
        "errors/403_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/403.html"
    )
    return render(
        request, template, {"is_admin_forbidden": is_admin_forbidden}, status=403
    )


def page_not_found(request, exception):
    """Custom 404 page."""
    _coerce_request_user_for_error_pages(request)
    template = (
        "errors/404_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/404.html"
    )
    return render(request, template, status=404)


def server_error(request):
    """Custom 500 page with minimal HTML fallback if template chain fails."""
    _coerce_request_user_for_error_pages(request)
    context = {"user": request.user}
    template = (
        "errors/500_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/500.html"
    )
    try:
        return render(request, template, context, status=500)
    except Exception:
        try:
            html = get_template("errors/500_minimal.html").render({})
        except Exception:
            html = (
                "<!doctype html><meta charset=utf-8>"
                "<title>Service interrupted</title>"
                "<h1>500 - service interrupted</h1>"
                "<p>Retry once. If it persists, contact support.</p>"
                "<p><a href='/'>Home</a> &middot; <a href='/-/version/'>Version</a></p>"
            )
        return HttpResponse(html, status=500, content_type="text/html; charset=utf-8")


def service_unavailable(request, exception=None):
    """Custom 503 page — maintenance mode and upstream overload."""
    _coerce_request_user_for_error_pages(request)
    template = (
        "errors/503_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/503.html"
    )
    return render(request, template, status=503)
