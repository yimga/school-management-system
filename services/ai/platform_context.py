"""Tier-specific context blocks (platform SRE vs school tenant)."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from services.ai.tenant_isolation import PlatformTier, TenantScope


def platform_operator_context_lines() -> list[str]:
    """Non-secret platform hints for super-admin / control-plane prompts."""
    lines = [
        "- Scope: platform-wide operator context (multi-tenant aggregate views only).",
        "- Indexed documentation scopes: config, help (run: python manage.py index_ai_knowledge).",
    ]
    webui = getattr(settings, "OPEN_WEBUI_URL", None)
    if webui:
        lines.append("- AI ops console URL is configured for operators (see OPEN_WEBUI_URL).")
    if getattr(settings, "AI_GATEWAY_ENABLED", True):
        lines.append("- AI gateway: enabled (Ollama-first, rules fallback).")
    return lines


def school_tenant_context_lines(school: Any | None) -> list[str]:
    """School-scoped hints without PII beyond public school name."""
    if school is None:
        return ["- Scope: authenticated school user (tenant binding pending on request)."]
    label = (
        getattr(school, "name", None)
        or getattr(school, "slug", None)
        or "active school"
    )
    country = getattr(school, "country_code", None) or ""
    lines = [
        f"- Active school: {label} (tenant-isolated; no cross-school data).",
        "- Help sources: published KB articles, approved FAQs, indexed help scope.",
    ]
    if country:
        lines.append(f"- Region/country code: {country} (locale and grading context).")
    return lines


def build_tier_context_block(scope: TenantScope, school: Any | None) -> str:
    if scope.tier == PlatformTier.PLATFORM_MANAGER:
        extras = platform_operator_context_lines()
        header = "[PLATFORM OPERATOR CONTEXT]"
    else:
        extras = school_tenant_context_lines(school)
        header = "[SCHOOL TENANT CONTEXT]"
    return header + "\n" + "\n".join(extras)
