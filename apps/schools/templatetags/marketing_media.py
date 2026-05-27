"""
Marketing media template tags: {% marketing_asset %}, {% marketing_viz %}, {% marketing_copy %}.
"""
from __future__ import annotations

from django import template
from django.templatetags.static import static

from apps.schools.marketing_media_matrix import marketing_copy_token, platform_viz_key_for_slug

register = template.Library()

_VIZ_PARTIALS = {
    "split_ledger": "marketing/viz/split_ledger.svg.html",
    "split_ledger_viz": "marketing/viz/split_ledger.svg.html",
    "transit_viz": "marketing/viz/transit_beacon.svg.html",
    "transit_beacon": "marketing/viz/transit_beacon.svg.html",
    "gradebook_viz": "marketing/viz/gradebook_frameworks.svg.html",
    "gradebook_frameworks": "marketing/viz/gradebook_frameworks.svg.html",
}


@register.simple_tag(takes_context=True)
def marketing_asset(context, asset_key: str) -> str:
    """Resolve static URL for regional loop or shared visual."""
    request = context.get("request")
    geo = getattr(request, "geo_context", None) or context.get("geo") or {}
    assets = geo.get("assets") or {}
    rel = assets.get(asset_key, "")
    if not rel:
        # Shared fallbacks
        fallbacks = {
            "sovereign_hero_loop_mp4": "marketing/video/loops/sovereign_default.mp4",
            "sovereign_hero_loop_webm": "marketing/video/loops/sovereign_default.webm",
            "admissions_flow_mp4": "marketing/video/loops/sovereign_default.mp4",
        }
        rel = fallbacks.get(asset_key, "")
    if not rel:
        return ""
    return static(rel)


@register.inclusion_tag("marketing/components/_marketing_viz_include.html", takes_context=True)
def marketing_viz(context, viz_key: str):
    partial = _VIZ_PARTIALS.get(viz_key, f"marketing/viz/{viz_key}.svg.html")
    return {"viz_partial": partial, "viz_key": viz_key}


@register.simple_tag
def marketing_platform_viz_key(page_slug: str) -> str:
    return platform_viz_key_for_slug(page_slug)


@register.inclusion_tag("marketing/components/_platform_visual_engine_strip.html", takes_context=True)
def marketing_platform_visual_strip(context):
    page = context.get("page") or {}
    slug = ""
    if hasattr(page, "slug"):
        slug = str(page.slug or "")
    elif isinstance(page, dict):
        slug = str(page.get("slug") or "")
    viz_key = platform_viz_key_for_slug(slug)
    show_apm = slug in {"platform-fees-payments"}
    return {"viz_key": viz_key, "show_apm_strip": show_apm}


@register.simple_tag(takes_context=True)
def marketing_copy(context, token: str) -> str:
    ml = context.get("marketing_local") or {}
    geo = context.get("geo") or {}
    cc = geo.get("country_code") or ml.get("country_code") or "US"
    return marketing_copy_token(cc, token, ml)
