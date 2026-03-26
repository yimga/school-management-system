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
