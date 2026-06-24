"""Templatetags for the Unified Wizard Framework.

Loaded via ``{% load wizard_extras %}``. Minimal, narrowly-scoped: just enough
to keep the wizard input partials free of view-layer special cases.
"""

from __future__ import annotations

from typing import Any

from django import template

register = template.Library()


@register.filter(name="dict_get")
def dict_get(value: Any, key: Any) -> Any:
    """``{{ some_dict|dict_get:key }}`` — returns ``None`` on missing key or non-dict input."""
    if not isinstance(value, dict):
        return None
    return value.get(key)


@register.filter(name="list_contains")
def list_contains(value: Any, item: Any) -> bool:
    """``{{ some_list|list_contains:value }}`` — boolean check."""
    if not isinstance(value, (list, tuple, set)):
        return False
    return item in value


@register.filter(name="humanize_wizard_token")
def humanize_wizard_token_filter(value: Any) -> str:
    """``{{ token|humanize_wizard_token }}`` — readable label for a wizard token.

    Resolves synthesized ``wizards.*`` slugs (and gettext catalog entries) to
    human text; passes resolver-supplied human labels through unchanged. Used
    wherever a raw ``label_token`` is rendered straight off a wizard/step/option
    object (stepper, index cards, choice lists) — the view layer already
    humanizes ``step_label`` / ``wizard_label`` in ``_build_context``.
    """
    from apps.setup_studio.wizard_labels import humanize_wizard_token

    return humanize_wizard_token(value)


@register.filter(name="health_summary_text")
def health_summary_text(value: Any) -> str:
    """Readable line from setup/launch ``health_summary`` dicts (detail, then label)."""
    if isinstance(value, dict):
        detail = value.get("detail")
        if detail:
            return str(detail)
        label = value.get("label")
        if label:
            return str(label)
        return ""
    if value in (None, ""):
        return ""
    return str(value)
