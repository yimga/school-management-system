"""
Marketing landing v2 — editorial redesign preview.

Self-contained view for the /v2 stakeholder-review surface. The template
hardcodes its own copy, but the inherited marketing_header.html and
marketing_footer.html still need the marketing context (nav primary,
footer links, brand mode flags). We reuse _marketing_context from
marketing_views so the editorial-styled inherited chrome renders fully.
"""

from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def marketing_landing_v2(request):
    """Editorial redesign preview at /v2 — noindex, unlinked from nav."""
    from apps.schools.marketing_views import (
        _get_country_from_request,
        _marketing_context,
    )

    geo_country = _get_country_from_request(request)
    ctx = _marketing_context(
        request,
        country_code=geo_country,
        language_code=(getattr(request, "LANGUAGE_CODE", "") or "en"),
        regional=False,
    )
    # /v2/ is the preview URL; the production homepage at / now also renders
    # this template via marketing_landing. Flag the preview path so it carries
    # noindex while / stays indexable.
    ctx["v2_preview"] = True
    return render(request, "schools/marketing_landing_v2.html", ctx)
