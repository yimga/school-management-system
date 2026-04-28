"""Template filters for pack catalog entitlement hints."""

from __future__ import annotations

from django import template

from apps.marketplace.pack_registry import pack_row_entitled

register = template.Library()


@register.filter
def pack_row_entitled_filter(school, row) -> bool:
    return bool(pack_row_entitled(school, row if isinstance(row, dict) else {}))
