"""Phase 8 declaration strip — one inclusion tag per full-page dashboard."""

from __future__ import annotations

from django import template

from apps.dashboard.phase8_declarations import get_phase8_declaration

register = template.Library()


@register.inclusion_tag("components/phase8_declaration_strip.html")
def phase8_dashboard_declaration(template_path: str) -> dict:
    """
    Render the structured declaration for a canonical dashboard template path.

    `template_path` must match a key in phase8_declarations.PHASE8_DECLARATIONS
    (same string as in phase7_dashboard_templates.PHASE7_DASHBOARD_TEMPLATES).
    """
    dec = get_phase8_declaration(template_path)
    return {"dec": dec}
