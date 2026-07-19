"""Template tags for guided tours and field explainers."""

from django import template
from django.utils.safestring import mark_safe

from apps.siteconfig.ui_field_help import get_ui_field_help

register = template.Library()


@register.inclusion_tag("partials/rmc_info_tag.html", takes_context=True)
def rmc_info_tag(
    context,
    entity="",
    field="",
    feature="",
    title="",
    body="",
    placement="top",
    what="",
    why="",
    watch_outs="",
    chips="",
    surface="",
):
    """
    Render an info icon with exceptional tip payload.

    Copy resolves from *feature*, *entity*+*field* (metadata catalog + static registry),
    or explicit *title* / *body*. Optional *what* / *why* / *watch_outs* / *chips* /
    *surface* power the fixed tip layer.
    """
    if title or body:
        resolved = {"title": title, "body": body}
    else:
        resolved = get_ui_field_help(entity or "", field or "", feature=feature or "")
    resolved_title = resolved.get("title") or title
    resolved_body = resolved.get("body") or body
    tip_what = what or resolved.get("what") or resolved_body
    tip_why = why or resolved.get("why") or ""
    tip_watch = watch_outs or resolved.get("watch_outs") or ""
    tip_chips = chips or resolved.get("chips") or ""
    if isinstance(tip_chips, (list, tuple)):
        tip_chips = "|".join(str(c) for c in tip_chips if c)
    tip_surface = surface or resolved.get("surface") or ""
    return {
        "title": resolved_title,
        "body": resolved_body,
        "what": tip_what,
        "why": tip_why,
        "watch_outs": tip_watch,
        "chips": tip_chips,
        "surface": tip_surface,
        "placement": placement,
        "label": resolved_title or field or feature,
        "entity": entity,
        "field": field,
        "feature": feature,
        "extra_class": context.get("rmc_info_extra_class", ""),
    }


@register.simple_tag(takes_context=True)
def mark_page_explain_bar_present(context):
    """Flag, on the request, that the page-explain (Flow Thread) bar is rendering here.

    The bar is shell chrome rendered ABOVE the page content, so this fires before
    any ``components/next_action_strip.html`` lower on the page is rendered. The
    standalone strip reads ``request.rmc_page_explain_bar_present`` and suppresses
    itself whenever the bar is present — the action then renders exactly once (in
    the bar), with no double strip. Pages whose shell does NOT mount the bar
    (studio embeds, developer console, marketing/login shells) never set this flag,
    so their standalone strip still renders — no next-action is ever erased.

    Returns an empty string so the tag emits no markup.
    """
    request = context.get("request")
    if request is not None:
        request.rmc_page_explain_bar_present = True
    return ""


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
