"""``{% load rmc_labels %}`` — render an internal token as words, never as a slug.

Replaces the ``|cut:"_"`` idiom, which deletes the separator and produces
``dailyoperations``. See ``apps/platform_runtime/display_labels.py`` for why
that filter can never be right on a word separator.
"""

from __future__ import annotations

from typing import Any

from django import template

from apps.platform_runtime.display_labels import humanize_token
from apps.platform_runtime.tenant_operational_lifecycle import (
    operational_state_label,
)

register = template.Library()


@register.filter(name="humanize_token")
def humanize_token_filter(value: Any) -> str:
    """``{{ key|humanize_token }}`` — ``input_completeness`` -> ``Input completeness``.

    For open sets where the token explains itself. A closed vocabulary gets a
    curated registry instead.
    """
    return humanize_token(value)


@register.filter(name="lifecycle_state_label")
def lifecycle_state_label_filter(value: Any) -> str:
    """``{{ state|lifecycle_state_label }}`` — the school-readable lifecycle state.

    ``conception`` is not "Conception" to a school; it is "Being created".
    Curated in ``tenant_operational_lifecycle.OPERATIONAL_STATE_LABELS``, next
    to the states themselves, so a new state without a label is a visible diff.
    """
    return operational_state_label(value)
