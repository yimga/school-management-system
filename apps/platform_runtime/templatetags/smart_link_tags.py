"""Wave T (v3.97.0 — 2026-05-26) — Smart-link template tag.

Usage:

    {% load smart_link_tags %}
    {% render_smart_links state="frozen.billing" persona="tenant_admin" %}

Templates pass a state token (registered in
``apps.platform_runtime.smart_links_kernel``) and an optional persona;
the tag iterates the registry, reverses URLs where possible (silently
skipping unresolvable entries — host context may not expose every
url_name), and renders Bootstrap-style buttons.

The tag is intentionally narrow: no slot for inline copy, no class-name
overrides. If a page needs richer chrome, render the buttons in template
markup and pass ``state`` only to ``get_smart_links``.
"""

from __future__ import annotations

from django import template
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.platform_runtime.smart_links_kernel import SmartLink, get_smart_links

register = template.Library()


_SEVERITY_CLASS = {
    "primary": "btn btn-primary",
    "secondary": "btn btn-outline-secondary",
    "danger": "btn btn-danger",
    "success": "btn btn-success",
}


def _resolve_href(link: SmartLink) -> str | None:
    """Return the final href for a SmartLink or ``None`` if unresolvable."""
    if link.mailto:
        return f"mailto:{link.mailto}"
    if link.url_name:
        try:
            return reverse(link.url_name, kwargs=link.kwargs or None)
        except NoReverseMatch:
            return None
    if link.href:
        return link.href
    return None


@register.simple_tag
def render_smart_links(state: str, persona: str = "any") -> str:
    """Render the smart-links block for a (state, persona) pair."""
    links = get_smart_links(state, persona=persona)
    rendered_rows: list[tuple[str, str, str, str]] = []
    for link in links:
        href = _resolve_href(link)
        if not href:
            continue
        btn_class = _SEVERITY_CLASS.get(link.severity, "btn btn-outline-secondary")
        icon_html = ""
        if link.icon:
            icon_html = format_html(
                '<i class="bi {} me-1" aria-hidden="true"></i>', link.icon,
            )
        rendered_rows.append((btn_class, href, str(icon_html), link.label))
    if not rendered_rows:
        return ""

    buttons_html = format_html_join(
        " ",
        '<a class="{} me-2 mb-2" href="{}">{}{}</a>',
        rendered_rows,
    )

    # Helper-text strip beneath the buttons (one row per link that supplied
    # helper_text). Renders only when at least one link contributed copy.
    helper_rows = [
        (link.icon or "bi-info-circle", link.label, link.helper_text)
        for link in links
        if link.helper_text and _resolve_href(link) is not None
    ]
    helper_html = ""
    if helper_rows:
        helper_html = format_html(
            '<ul class="list-unstyled small text-muted mb-0 mt-2">{}</ul>',
            format_html_join(
                "",
                '<li><i class="bi {} me-1" aria-hidden="true"></i>'
                "<strong>{}:</strong> {}</li>",
                helper_rows,
            ),
        )

    return mark_safe(
        format_html(
            '<div class="rmc-smart-links" data-rmc-smart-links="{}">'
            '<div class="d-flex flex-wrap">{}</div>{}</div>',
            state,
            buttons_html,
            helper_html,
        ),
    )
