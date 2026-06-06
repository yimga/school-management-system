"""Views for the honest 'RunMyCampus vs <competitor>' SEO comparison pages.

Mirrors apps/schools/competitive_marketing_views.py::marketing_story_page —
slug lookup, 404 on miss, personality context, render. Data + honesty contract
live in apps/schools/marketing_competitor_comparisons.py.
"""

from __future__ import annotations

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.schools.marketing_competitor_comparisons import comparison_for_slug


@require_GET
def competitor_compare_page(request, slug: str):
    from apps.schools.marketing_personality import marketing_personality_context

    comparison = comparison_for_slug(slug)
    if not comparison:
        raise Http404("Unknown comparison")

    ctx = {
        **comparison,
        "seo_title": comparison["seo_title"],
        "seo_description": comparison["seo_description"],
        "marketing_page_slug": "compare",
        **marketing_personality_context("compare"),
    }
    return render(request, "marketing/pages/competitor_compare.html", ctx)
