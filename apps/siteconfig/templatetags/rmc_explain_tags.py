"""Template tags for guided tours and field explainers."""

from django import template
from django.utils.safestring import mark_safe

from apps.siteconfig.ui_field_help import get_ui_field_help

register = template.Library()


@register.inclusion_tag("partials/rmc_info_tag.html", takes_context=True)
def rmc_info_tag(context, entity="", field="", feature="", title="", body="", placement="top"):
    """
    Render an info icon with popover copy.

    Copy resolves from *feature*, *entity*+*field* (metadata catalog + static registry),
    or explicit *title* / *body*.
    """
    if title or body:
        resolved = {"title": title, "body": body}
    else:
        resolved = get_ui_field_help(entity or "", field or "", feature=feature or "")
    return {
        "title": resolved.get("title") or title,
        "body": resolved.get("body") or body,
        "placement": placement,
        "label": resolved.get("title") or title or field or feature,
        "extra_class": context.get("rmc_info_extra_class", ""),
    }


@register.simple_tag
def rmc_tour_trigger(context_name, *, steps_url="", complete_url="", label=""):
    """Emit a tour trigger button (caller supplies translated label)."""
    from django.utils.html import format_html

    attrs = f'data-tour-trigger="{context_name}"'
    if steps_url:
        attrs += f' data-tour-steps-url="{steps_url}"'
    if complete_url:
        attrs += f' data-tour-complete-url="{complete_url}"'
    text = label or "Tour"
    return mark_safe(
        format_html(
            '<button type="button" class="btn btn-outline-secondary btn-sm" {}>{}</button>',
            mark_safe(attrs),
            text,
        )
    )
