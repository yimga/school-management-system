"""
Dedicated error views for multi-tenant flows (e.g. School Not Found 404).
"""

import logging
import os

from django.http import HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)

# Self-contained 404 — no templates, no context processors, no DB. Last-resort
# fallback so the tenant 404 handler renders even when a tenant context processor
# (the full shell stack) is exactly what raised. Without it, an unmatched path
# (e.g. /sw-manifest.json, /offline/) escalates 404 -> 500 on tenant subdomains.
_STATIC_TENANT_404 = (
    "<!doctype html><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width, initial-scale=1'>"
    "<title>Not found · RunMyCampus</title>"
    "<h1>404 - not found</h1>"
    "<p>The page you requested doesn't exist.</p>"
    "<p><a href='/'>Home</a></p>"
)


def school_not_found(request):
    """
    Branded "School Not Found" bento-style 404 when a subdomain or /t/<slug>/
    does not map to any tenant. Use in middleware or as handler404 for tenant routes.

    MUST NOT escalate to 500: the branded template runs the full tenant context-
    processor stack, and one of those processors can raise for an anonymous /
    unmatched-path hit (the bug that made /sw-manifest.json and /offline/ return
    500 on tenant subdomains). Fall back to a self-contained 404 on any failure.
    """
    try:
        return render(request, "schools/404_tenant.html", status=404)
    except Exception:
        logger.warning(
            "school_not_found: branded 404 render failed; serving static 404",
            exc_info=True,
        )
        return HttpResponse(
            _STATIC_TENANT_404, status=404, content_type="text/html; charset=utf-8"
        )


def _school_display_name_for_public(school) -> str:
    """
    Display name for a school on platform surfaces (e.g. school-not-found).
    Avoids showing the seeded default tenant brand on public platform surfaces.
    """
    name = (school.name or "").strip()
    if not name:
        return school.slug or "School"
    default_slug = (os.environ.get("DEFAULT_TENANT_SLUG") or "").strip().lower()
    school_slug = (getattr(school, "slug", "") or "").strip().lower()
    if default_slug and school_slug == default_slug:
        return school.slug or "School"
    return name


def school_not_found_public(request):
    """
    Branded root-domain 404 page for unknown tenant subdomains.
    """
    from apps.schools.pending_tenant_discovery import (
        lookup_school_by_slug_or_subdomain,
        pending_school_public_context,
        search_schools_for_public_finder,
    )

    query = (request.GET.get("slug") or request.GET.get("q") or "").strip()
    pending_ctx: dict = {}
    if query:
        matched = lookup_school_by_slug_or_subdomain(query)
        if matched is not None:
            pending_ctx = pending_school_public_context(matched)

    results = search_schools_for_public_finder(request, query)

    context = {"query": query, "results": results, **pending_ctx}
    return render(
        request,
        "schools/school_not_found.html",
        context,
        status=404 if not pending_ctx else 200,
    )
