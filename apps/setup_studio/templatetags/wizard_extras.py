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
