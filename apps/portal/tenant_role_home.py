"""Tenant role-home hero + legacy dashboard gate (Preview Shell 100x)."""

from __future__ import annotations

from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.siteconfig.models_support import filter_portal_items
from apps.siteconfig.config_service import get_effective_site_settings


def role_home_show_legacy(request: HttpRequest) -> bool:
    """Opt-in full legacy stack via ``?simple=1`` (matches parent simplified mode)."""
    raw = request.GET.get("simple", "")
    return str(raw).strip().lower() in {"1", "true", "yes", "legacy"}


def tp_hero_ai_tier_line() -> str:
    """PII-safe one-line assist tier summary (deployment profile chain, no secrets)."""
    from services.ai_deployment_posture import default_tier_chain_for_profile

    label_map = {
        "litellm": str(_("Cloud")),
        "ollama": str(_("Local")),
        "rules": str(_("Guided")),
    }
    chain = default_tier_chain_for_profile()
    parts = [label_map.get(tier, tier) for tier in chain]
    return str(_("Assist tier: %(tiers)s") % {"tiers": " → ".join(parts)})


def build_tp_hero_context(
    request: HttpRequest,
    *,
    role: str,
    children_names: str = "",
    has_fees_due: bool = False,
) -> dict[str, object]:
    site = get_effective_site_settings(request=request)
    portal_quick_actions = filter_portal_items(
        getattr(site, "portal_quick_actions", None) or [], role
    )
    return {
        "tp_greeting_role": role,
        "tp_greeting_children_names": children_names,
        "portal_quick_actions": portal_quick_actions,
        "has_fees_due": has_fees_due,
        "tp_hero_ai_tier_line": tp_hero_ai_tier_line(),
    }
