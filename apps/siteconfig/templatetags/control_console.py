"""Inclusion tags for operator decision-console strips (Phase 3–4 control surfaces)."""

from django import template

register = template.Library()


@register.inclusion_tag("siteconfig/partials/operator_console_strip.html", takes_context=True)
def operator_console_strip(context):
    request = context.get("request")
    if not request:
        return {"operator_quick_links": [], "why_enabled_summary": ""}
    from apps.siteconfig.control_outcome_center import (
        WHY_ENABLED_SUMMARY,
        build_feature_control_operator_quick_links,
    )

    return {
        "operator_quick_links": build_feature_control_operator_quick_links(request),
        "why_enabled_summary": WHY_ENABLED_SUMMARY,
    }


@register.filter
def text_on_brand(primary_hex):
    """Readable ink (dark or light) for text placed on the given brand color.

    Lets the tenant shell set ``--text-on-brand`` adaptively, so white-on-brand
    headers never wash out on a light school brand. Falls back to white.
    """
    from apps.siteconfig.contrast_guard import text_color_for_background

    try:
        return text_color_for_background(str(primary_hex or "").strip())
    except Exception:  # noqa: BLE001 — never break rendering over one color
        return "#ffffff"
