"""
Configurable AI chrome SOT — URLs, feature flags, and UI copy for copilot surfaces.

Cascade (no hardcoded product behavior in JS/templates):
  1. Tenant ``SiteSettings.backend_feature_flags`` (+ school.settings dict)
  2. Platform runtime effective flags
  3. Operator cockpit ``ai_copilot_rail`` (manager rail only)
  4. Django settings / env (gateway posture only)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from apps.portal.help_governance import (
    ai_assistant_panel_enabled_for_request,
    ai_help_enabled_for_request,
    parent_student_help_surface_policy,
)

logger = logging.getLogger(__name__)

__all__ = [
    "resolve_ai_chrome_config",
    "ai_chrome_config_json",
    "ai_copilot_permissions_for_user",
    "ai_copilot_query_api_enabled_for_request",
]

_FLAG_ERRORS = (AttributeError, ImportError, LookupError, TypeError, ValueError)


def _reverse(name: str, *, urlconf: str | None = None) -> str:
    try:
        if urlconf:
            return reverse(name, urlconf=urlconf)
        return reverse(name)
    except NoReverseMatch:
        logger.debug("ai_chrome_config: NoReverseMatch for %s", name)
        return ""


def _effective_flags(request) -> dict[str, Any]:
    try:
        school = getattr(request, "school", None)
        if school is not None:
            raw = getattr(school, "settings", None) or {}
            if isinstance(raw, dict):
                nested = raw.get("backend_feature_flags") or {}
                if isinstance(nested, dict) and nested:
                    return dict(nested)
        from apps.platform_runtime.helpers import get_effective_flags

        return dict(get_effective_flags(request) or {})
    except _FLAG_ERRORS:
        return {}


def _flag(flags: dict[str, Any], key: str, default: Any) -> Any:
    if key in flags:
        return flags[key]
    return default


def _ui_pack(flags: dict[str, Any]) -> dict[str, Any]:
    raw = flags.get("ai_copilot_ui")
    return dict(raw) if isinstance(raw, dict) else {}


def _manager_rail_enabled(request, flags: dict[str, Any]) -> bool:
    if getattr(request, "public_host_kind", None) != "manager":
        return False
    try:
        from apps.siteconfig.cockpit_context import cockpit_context

        ctx = cockpit_context(request)
        acr = (ctx.get("cockpit") or {}).get("ai_copilot_rail") or {}
        if "enabled" in acr:
            return bool(acr.get("enabled"))
    except _FLAG_ERRORS:
        logger.debug("ai_chrome_config: cockpit rail flag read failed", exc_info=True)
    return bool(_flag(flags, "enable_manager_ai_copilot_rail", True))


def _tenant_rail_enabled(request, flags: dict[str, Any]) -> bool:
    if getattr(request, "public_host_kind", None) == "manager":
        return False
    if getattr(request, "school", None) is None:
        return False
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not ai_help_enabled_for_request(request):
        return False
    try:
        from apps.siteconfig.cockpit_context import cockpit_context

        ctx = cockpit_context(request)
        acr = (ctx.get("cockpit") or {}).get("ai_copilot_rail") or {}
        if "enabled" in acr:
            return bool(acr.get("enabled"))
    except _FLAG_ERRORS:
        logger.debug("ai_chrome_config: tenant rail flag read failed", exc_info=True)
    return bool(_flag(flags, "enable_tenant_ai_copilot_rail", True))


def ai_copilot_permissions_for_user(user) -> dict[str, Any]:
    """RBAC map for floating copilot (mirrors ai_copilot_settings)."""
    from services.ai_copilot_rbac import build_copilot_permissions

    return build_copilot_permissions(user)


def _provider_status() -> dict[str, Any]:
    try:
        from apps.portal.ai_provider import get_public_ai_provider_status

        return get_public_ai_provider_status(include_health=True)
    except _FLAG_ERRORS:
        rules = bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True))
        return {
            "has_live_provider": False,
            "reachable": False,
            "rules_fallback_enabled": rules,
        }


def resolve_ai_chrome_config(request) -> dict[str, Any]:
    """Build the full chrome config dict for templates and page-data islands."""
    user = getattr(request, "user", None)
    flags = _effective_flags(request)
    ui = _ui_pack(flags)
    status = _provider_status()

    rules_fallback = bool(status.get("rules_fallback_enabled"))
    backend_enabled = (
        bool(status.get("has_live_provider"))
        or bool(status.get("reachable"))
        or rules_fallback
    )
    provider_name = ""
    live_kind = status.get("live_provider_kind")
    if status.get("has_live_provider") and live_kind:
        provider_name = str(live_kind)
    elif rules_fallback:
        provider_name = "rules"
    else:
        for provider in status.get("preference", []):
            providers = status.get("providers") or {}
            if not isinstance(providers, dict):
                continue
            provider_cfg = providers.get(provider, {})
            if isinstance(provider_cfg, dict) and provider_cfg.get("configured"):
                provider_name = str(provider)
                break

    urlconf = getattr(request, "urlconf", None)
    urls = {
        "copilot_query": _reverse("ai_copilot_query", urlconf=urlconf),
        "health": _reverse("ai_health", urlconf=urlconf),
        "permissions": _reverse("ai_permissions", urlconf=urlconf),
        "limits": _reverse("ai_copilot_limits", urlconf=urlconf),
        "config": _reverse("ai_copilot_config", urlconf=urlconf),
        "copilot_rail_context": _reverse("studio_os:copilot_rail_context", urlconf=urlconf),
        "copilot_rail_insights": _reverse("studio_os:copilot_rail_insights", urlconf=urlconf),
        "copilot_rail_send": _reverse("studio_os:copilot_rail_send", urlconf=urlconf),
        "copilot_rail_send_stream": _reverse(
            "studio_os:copilot_rail_send_stream", urlconf=urlconf
        ),
        "ai_stream": _reverse("portal:ai_stream", urlconf=urlconf),
        "browser_inference_config": _reverse(
            "browser_inference_config", urlconf=urlconf
        ),
        "local_voice_transcribe": _reverse(
            "local_voice_transcribe", urlconf=urlconf
        ),
        "local_voice_synthesize": _reverse(
            "local_voice_synthesize", urlconf=urlconf
        ),
    }

    max_chars_raw = ui.get("floating_max_message_chars", flags.get("ai_copilot_max_message_chars", 500))
    try:
        max_message_chars = max(100, min(int(max_chars_raw), 4000))  # magic-number-allow: ai-message-char-cap
    except (TypeError, ValueError):
        max_message_chars = 500

    offline_hint = str(
        ui.get("offline_hint")
        or flags.get("ai_copilot_offline_hint")
        or ""
    ).strip()

    user_role = "USER"
    user_display_name = ""
    if user is not None and getattr(user, "is_authenticated", False):
        user_role = (getattr(user, "role", "USER") or "").upper()
        user_display_name = (
            getattr(user, "first_name", None)
            or getattr(user, "username", None)
            or ""
        )

    return {
        "urls": urls,
        "features": {
            "help_assistant": ai_help_enabled_for_request(request),
            "floating_panel": ai_assistant_panel_enabled_for_request(request),
            "manager_rail": _manager_rail_enabled(request, flags),
            "tenant_rail": _tenant_rail_enabled(request, flags),
            "copilot_api_enabled": bool(
                _flag(flags, "enable_ai_copilot_query_api", True)
            ),
            "backend_enabled": backend_enabled,
            "rules_fallback_enabled": rules_fallback,
            "browser_inference": bool(
                getattr(settings, "BROWSER_AI_ENABLED", False)
            ),
            "local_voice": bool(getattr(settings, "LOCAL_VOICE_ENABLED", False)),
        },
        "ui": {
            "floating_panel_title": str(
                ui.get("floating_panel_title") or flags.get("ai_copilot_panel_title") or ""
            ),
            "floating_input_placeholder": str(
                ui.get("floating_input_placeholder")
                or flags.get("ai_copilot_input_placeholder")
                or ""
            ),
            "floating_max_message_chars": max_message_chars,
            "offline_hint": offline_hint,
        },
        "permissions": ai_copilot_permissions_for_user(user),
        "provider_name": provider_name,
        "user_role": user_role,
        "user_display_name": str(user_display_name),
        "parent_student_policy": parent_student_help_surface_policy(request),
        "posture": {
            "reachable": bool(status.get("reachable")),
            "degraded": bool(status.get("degraded")),
            "provider": status.get("provider"),
            "posture_label": status.get("posture_label"),
        },
        "local_ai": {
            "voice_languages": list(
                getattr(settings, "LOCAL_VOICE_LANGUAGES", ["en"])
            ),
            "voice_max_audio_bytes": int(
                getattr(settings, "LOCAL_VOICE_MAX_AUDIO_BYTES", 2_000_000)
            ),
        },
    }


def ai_chrome_config_json(request) -> str:
    """JSON for ``<script type=\"application/json\" id=\"page-data-rmc-ai-chrome\">``."""
    return json.dumps(resolve_ai_chrome_config(request), separators=(",", ":"))


def ai_copilot_query_api_enabled_for_request(request) -> bool:
    flags = _effective_flags(request)
    return bool(_flag(flags, "enable_ai_copilot_query_api", True))
