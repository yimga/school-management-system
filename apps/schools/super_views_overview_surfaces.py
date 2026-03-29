"""
Schools list and analytics overview (BR-12 split from super_views).
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.platform_runtime.models import (
    PlatformOperatorSuperAnalyticsOverviewLink,
    PlatformOperatorSuperSchoolsListLink,
)
from apps.registries.services import WEDGE_14_22_SECTOR_CODES

from .models import School


@require_GET
def super_schools_list(request):
    """Phase 7: Paginated list of all schools; optional filters and link to tenant 360 / backoffice. Wedge 14–22: segment by primary_sector."""
    qs = School.objects.all().order_by("name")
    # Optional filters
    is_active = request.GET.get("is_active")
    if is_active is not None:
        if is_active.lower() in ("1", "true", "yes"):
            qs = qs.filter(is_active=True)
        elif is_active.lower() in ("0", "false", "no"):
            qs = qs.filter(is_active=False)
    country_code = request.GET.get("country_code", "").strip()
    if country_code:
        qs = qs.filter(country_code=country_code)
    primary_sector = request.GET.get("primary_sector", "").strip().upper()
    if primary_sector and primary_sector in WEDGE_14_22_SECTOR_CODES:
        qs = qs.filter(primary_sector=primary_sector)
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(slug__icontains=search)
            | Q(subdomain__icontains=search)
        )
    # Sector cohort counts (for segment-by-sector links)
    sector_counts = dict(
        School.objects.filter(primary_sector__in=WEDGE_14_22_SECTOR_CODES)
        .values("primary_sector")
        .annotate(count=Count("id"))
        .values_list("primary_sector", "count")
    )
    sector_choices = [
        {
            "code": c,
            "name": c.replace("_", " ").title(),
            "count": sector_counts.get(c, 0),
        }
        for c in WEDGE_14_22_SECTOR_CODES
    ]
    paginator = Paginator(qs, 25)
    page_number = request.GET.get("page", 1)
    page = paginator.get_page(page_number)
    admin_schools_url = None
    operator_super_schools_list_links = list(
        PlatformOperatorSuperSchoolsListLink.objects.order_by("sort_order", "slug")
    )
    return render(
        request,
        "schools/super_schools_list.html",
        {
            "page": page,
            "dashboard_url": reverse("super:dashboard"),
            "admin_schools_url": admin_schools_url,
            "is_active_filter": is_active if is_active is not None else "",
            "country_code_filter": country_code,
            "primary_sector_filter": primary_sector,
            "sector_choices": sector_choices,
            "search_query": search,
            "operator_super_schools_list_links": operator_super_schools_list_links,
        },
    )


def super_analytics_overview(request):
    """Phase 13: Analytics and observability — tenant health, adoption, feature usage, workflow success."""
    operator_super_analytics_overview_links = list(
        PlatformOperatorSuperAnalyticsOverviewLink.objects.order_by(
            "sort_order", "slug"
        )
    )
    return render(
        request,
        "schools/super_analytics_overview.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "operator_super_analytics_overview_links": operator_super_analytics_overview_links,
        },
    )
