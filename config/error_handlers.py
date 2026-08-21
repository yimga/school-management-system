"""
Shared Django error-page handlers for root, manager, and tenant urlconfs.

Kept in a dedicated module so ``config.manager_urls`` can import handlers without
re-entering ``config.urls`` during urlconf load (avoids circular ImportError).
"""

from __future__ import annotations

import logging
import re

from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import get_template

logger = logging.getLogger(__name__)


def error_reference(request) -> str:
    """Correlator a user can quote so an operator can find the log line.

    ``ObservabilityMiddleware`` stamps ``request.request_id`` on every request and
    echoes it as the ``X-Request-ID`` response header, and the structured log
    formatter prints ``request_id=<id>`` on every line. The error PAGE never showed
    it, so a tenant reporting "I got a 500" handed over nothing searchable and the
    only way to find the traceback was to guess the timestamp. Surfacing it turns
    that into one grep.

    Never raises and never invents a value: an empty string means "no id on this
    request", and the template simply omits the reference line.
    """
    try:
        value = getattr(request, "request_id", "") or ""
    except Exception:  # noqa: BLE001 - an error page must never fail
        return ""
    value = str(value).strip()
    # Client-supplied (the middleware honours an inbound X-Request-ID header), so
    # treat it as untrusted: bound the length and keep it to id-safe characters
    # before it reaches a template or a log line.
    if not value or len(value) > 64:
        return ""
    return value if re.fullmatch(r"[A-Za-z0-9._:-]+", value) else ""


def _static_error_html(code: str, title: str, message: str) -> str:
    """Fully self-contained error markup — no templates, no context, no DB.

    Used as the last-resort fallback so an error page can render even when the
    template chain or a context processor is exactly what failed.
    """
    return (
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{title} · RunMyCampus</title>"
        f"<h1>{code} - {title}</h1>"
        f"<p>{message}</p>"
        "<p><a href='/'>Home</a></p>"
    )


def _safe_error_render(request, template, *, status, fallback_html, context=None):
    """Render a branded error template but NEVER raise.

    Error pages must survive a failing context processor — e.g. a tenant-scoped
    processor that performs DB work for an anonymous hit — otherwise a 404/403/503
    escalates into a 500 (the bug that made ``/sw-manifest.json`` and ``/offline/``
    return 500 on tenant subdomains). Mirrors the long-standing ``server_error``
    fallback so every handler is equally bulletproof.
    """
    try:
        return render(request, template, context or {}, status=status)
    except Exception:
        logger.warning(
            "error-page render failed (template=%s status=%s); serving static fallback",
            template,
            status,
            exc_info=True,
        )
        return HttpResponse(
            fallback_html, status=status, content_type="text/html; charset=utf-8"
        )


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
    return _safe_error_render(
        request,
        template,
        status=403,
        context={"is_admin_forbidden": is_admin_forbidden},
        fallback_html=_static_error_html(
            "403", "Access denied", "You don't have permission to view this page."
        ),
    )


def page_not_found(request, exception):
    """Custom 404 page."""
    _coerce_request_user_for_error_pages(request)
    template = (
        "errors/404_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/404.html"
    )
    return _safe_error_render(
        request,
        template,
        status=404,
        fallback_html=_static_error_html(
            "404", "Not found", "The page you requested doesn't exist."
        ),
    )


def server_error(request):
    """Custom 500 page with minimal HTML fallback if template chain fails."""
    _coerce_request_user_for_error_pages(request)
    context = {"user": request.user, "error_reference": error_reference(request)}
    template = (
        "errors/500_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/500.html"
    )
    try:
        return render(request, template, context, status=500)
    except Exception:
        try:
            html = get_template("errors/500_minimal.html").render(
                {"error_reference": error_reference(request)}
            )
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
    _context = {"error_reference": error_reference(request)}
    template = (
        "errors/503_control_plane.html"
        if getattr(request, "public_host_kind", None) == "manager"
        else "errors/503.html"
    )
    return _safe_error_render(
        request,
        template,
        status=503,
        fallback_html=_static_error_html(
            "503",
            "Temporarily unavailable",
            "We're briefly offline for maintenance. Please retry shortly.",
        ),
        context=_context,
    )
