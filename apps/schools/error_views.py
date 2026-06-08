"""
Dedicated error views for multi-tenant flows (e.g. School Not Found 404).
"""

import os

from django.shortcuts import render


def school_not_found(request):
    """
    Branded "School Not Found" bento-style 404 when a subdomain or /t/<slug>/
    does not map to any tenant. Use in middleware or as handler404 for tenant routes.
    """
    return render(
        request,
        "schools/404_tenant.html",
        status=404,
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
