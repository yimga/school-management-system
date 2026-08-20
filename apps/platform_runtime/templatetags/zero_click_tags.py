"""Wave U (v3.99.0 — 2026-05-27) — Zero-Click-Intuition template tags.

Resolves the Action Hub, Empty-State Card, and Text-Shield primitives at
render time. Each tag silently no-ops when its dependency is missing
(unresolvable URL / unknown wizard slug) — these are UX enhancements, not
load-bearing APIs, so a stale registry must never crash a page.
"""

from __future__ import annotations

import logging

from django import template
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
from django.utils.html import escape, format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.platform_runtime.action_hub_kernel import ActionHub, HubAction
from apps.platform_runtime.click_budget import clicks_saved_for_path
from apps.platform_runtime.empty_state_kernel import EmptyStateCard, get_empty_state
from apps.platform_runtime.smart_links_kernel import PERSONA_ANY, get_smart_links
from apps.platform_runtime.table_grammar_kernel import (
    Column,
    MAX_PRIMARY_COLUMNS,
    build_columns_from_dicts,
    truncate_columns,
)

logger = logging.getLogger(__name__)

register = template.Library()


def _with_query(path: str, query: str) -> str:
    """Append a querystring to a reversed path, so the path stays out of source."""
    if not query:
        return path
    return f"{path}{'&' if '?' in path else '?'}{query}"


# --- Action Hub -----------------------------------------------------------


def _resolve_hub_href(action: HubAction, persona: str = "") -> str | None:
    """Pick the first resolvable target from the HubAction.

    A ``url_name`` is reversed against the request's urlconf, so a chip whose
    route is absent on this host is dropped rather than rendered. A literal
    ``href`` used to be returned unchecked, which is how six chips shipped
    pointing at paths that only exist on ``config.urls``: a 404 wearing a
    button. Literal paths are now resolved before use and dropped if they
    lead nowhere — the same treatment the named route already got.
    """
    if action.url_name:
        try:
            return _with_query(reverse(action.url_name), action.query)
        except NoReverseMatch:
            pass
    if action.href:
        try:
            resolve(action.href.split("?")[0])
        except Resolver404:
            logger.warning(
                "action hub: dropping %r — %r resolves on no route for this host",
                action.key,
                action.href,
            )
        else:
            return action.href
    if action.state_token:
        # Defer to the smart_links registry: take the first resolvable link.
        # "Resolvable" has to mean resolvable, including for literal paths —
        # the admissions chip reached this branch and handed back a path that
        # existed on no host at all.
        #
        # The persona MUST be passed. `_REGISTRY` is keyed by (state, persona)
        # and `get_smart_links` defaults to persona="any", whose fallback is a
        # no-op; every entry these chips need is filed under a real persona.
        # Called without it, this branch had never once returned a link, so the
        # safeguarding, admissions, overdue-balance and transcript-hold chips —
        # the danger-severity ones — were dropped on the floor in silence.
        for link in get_smart_links(action.state_token, persona or PERSONA_ANY):
            if link.url_name:
                try:
                    return reverse(link.url_name, kwargs=link.kwargs or None)
                except NoReverseMatch:
                    continue
            if link.href:
                try:
                    resolve(link.href.split("?")[0])
                except Resolver404:
                    continue
                return link.href
            if link.mailto:
                return f"mailto:{link.mailto}"
    return None


@register.simple_tag
def render_action_hub(hub: ActionHub | None) -> str:
    """Render the Action Hub strip from an ``ActionHub`` instance."""
    if hub is None:
        return ""
    actions = hub.non_empty_actions
    if not actions:
        return ""

    rows: list[tuple[str, str, str, str, str, int]] = []
    for action in actions:
        href = _resolve_hub_href(action, hub.persona)
        if not href:
            continue
        count_html = ""
        if action.count > 0:
            count_html = format_html(
                '<span class="rmc-action-hub__count">{}</span>',
                action.count,
            )
        icon_html = ""
        if action.icon:
            icon_html = format_html(
                '<i class="bi {}" aria-hidden="true"></i>', action.icon,
            )
        rows.append((
            href,
            action.severity,
            str(icon_html),
            action.label,
            str(count_html),
            clicks_saved_for_path(href),
        ))
    if not rows:
        return ""

    # data-rmc-clicks-saved is the chip's own claim about what it spared the
    # reader, derived from its destination. It sits next to the click-tracking
    # instrumentation that records what readers actually did, so the claim and
    # the evidence can be compared instead of the claim being taken on trust.
    chips_html = format_html_join(
        "",
        (
            '<a class="rmc-action-hub__chip" href="{}" data-rmc-severity="{}"'
            ' data-rmc-clicks-saved="{}">{}<span>{}</span>{}</a>'
        ),
        [(r[0], r[1], r[5], r[2], r[3], r[4]) for r in rows],
    )
    return mark_safe(
        format_html(
            '<div class="rmc-action-hub" role="region" aria-label="Quick actions">{}</div>',
            chips_html,
        ),
    )


# --- Empty-state card -----------------------------------------------------


def _resolve_empty_state_cta(card: EmptyStateCard) -> str | None:
    """Wizard slug -> URL (best-effort); url_name -> reverse."""
    if card.cta_url_name:
        try:
            return reverse(card.cta_url_name, kwargs=card.cta_kwargs or None)
        except NoReverseMatch:
            return None
    if card.cta_wizard_slug:
        # Try the unified-wizard launcher conventions. Silently degrade.
        candidates = (
            ("setup_studio:wizard_launch", {"slug": card.cta_wizard_slug}),
            ("setup_studio:wizard", {"slug": card.cta_wizard_slug}),
            ("wizard_launch", {"slug": card.cta_wizard_slug}),
        )
        for name, kwargs in candidates:
            try:
                return reverse(name, kwargs=kwargs)
            except NoReverseMatch:
                continue
        return None
    return None


def _resolve_helper(card: EmptyStateCard) -> str | None:
    if not card.helper_link_url_name:
        return None
    try:
        return reverse(card.helper_link_url_name)
    except NoReverseMatch:
        return None


@register.simple_tag
def render_empty_state(domain: str, persona: str = "any") -> str:
    """Render the empty-state card for a (domain, persona) pair."""
    card = get_empty_state(domain, persona=persona)
    if card is None:
        return ""

    cta_html = ""
    cta_href = _resolve_empty_state_cta(card)
    if cta_href and card.cta_label:
        cta_html = format_html(
            '<a class="rmc-empty-state__cta" href="{}">'
            '<i class="bi bi-arrow-right-circle" aria-hidden="true"></i>'
            "<span>{}</span></a>",
            cta_href,
            card.cta_label,
        )

    helper_html = ""
    helper_href = _resolve_helper(card)
    if helper_href and card.helper_link_label:
        helper_html = format_html(
            '<p class="rmc-empty-state__helper"><a href="{}">{}</a></p>',
            helper_href,
            card.helper_link_label,
        )

    return mark_safe(
        format_html(
            '<section class="rmc-empty-state" data-rmc-severity="{}" data-rmc-domain="{}">'
            '<div class="rmc-empty-state__icon"><i class="bi {}" aria-hidden="true"></i></div>'
            '<h3 class="rmc-empty-state__headline">{}</h3>'
            '<p class="rmc-empty-state__body">{}</p>'
            "{}{}</section>",
            card.severity,
            domain,
            card.icon,
            card.headline,
            card.body,
            cta_html,
            helper_html,
        ),
    )


# --- Text shield ----------------------------------------------------------


@register.simple_tag
def text_shield(value: str, max_chars: int = 0) -> str:
    """Wrap a string in the text-shield primitive.

    When ``max_chars`` > 0 and the string is longer, the visible label is
    truncated to ``max_chars`` and the full value lives in ``data-rmc-full``
    so the hover-tooltip CSS can surface it without layout shift.
    """
    if value is None:
        return ""
    text = str(value)
    full = text
    visible = text
    truncated = False
    if max_chars and len(text) > max_chars:
        visible = text[: max(1, max_chars - 1)].rstrip() + "…"
        truncated = True

    if truncated:
        return mark_safe(
            f'<span class="rmc-text-shield" data-rmc-full="{escape(full)}">'
            f'{escape(visible)}</span>'
        )
    return mark_safe(f'<span class="rmc-text-shield">{escape(visible)}</span>')


# --- 5-column table grammar -----------------------------------------------


def _columns_from_arg(columns) -> list[Column]:
    if isinstance(columns, (list, tuple)):
        if columns and isinstance(columns[0], Column):
            return list(columns)
        return build_columns_from_dicts(columns)
    if isinstance(columns, str):
        import json

        parsed = json.loads(columns)
        return build_columns_from_dicts(parsed)
    raise TypeError("columns must be a sequence of dicts, Column instances, or JSON string")


@register.simple_tag
def truncate_table_columns(columns, persona: str = "any", max_visible: int = MAX_PRIMARY_COLUMNS):
    """Partition table columns into visible (≤5) and drawer sets.

    Usage::

        {% truncate_table_columns column_defs persona as table_cols %}
        {% for col in table_cols.visible %}…{% endfor %}
    """
    cols = _columns_from_arg(columns)
    result = truncate_columns(cols, persona=persona, max_visible=int(max_visible))
    return {
        "visible": result.visible_columns,
        "drawer": result.drawer_columns,
        "overflow_count": result.overflow_count,
        "fits_without_drawer": result.fits_without_drawer,
    }


@register.filter
def column_label(column: Column) -> str:
    return column.label if isinstance(column, Column) else str(column)


@register.filter
def column_key(column: Column) -> str:
    return column.key if isinstance(column, Column) else str(column)
