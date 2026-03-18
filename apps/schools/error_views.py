"""
Dedicated error views for multi-tenant flows (e.g. School Not Found 404).
"""

import os

from django.db.models import Q
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
    from apps.schools.models import School
    from apps.schools.section8_views import _build_school_portal_url

    query = (request.GET.get("slug") or request.GET.get("q") or "").strip()
    results = []
    if len(query) >= 2:
        schools = (
            School.objects.filter(is_active=True)
            .filter(
                Q(name__icontains=query)
                | Q(slug__icontains=query)
                | Q(subdomain__icontains=query)
            )
            .order_by("name")[:8]
        )
        for school in schools:
            results.append(
                {
                    "name": _school_display_name_for_public(school),
                    "slug": school.slug,
                    "portal_url": _build_school_portal_url(request, school),
                }
            )
    return render(
        request,
        "schools/school_not_found.html",
        {"query": query, "results": results},
        status=404,
    )
