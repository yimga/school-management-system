"""
AI provider abstraction — local-first, disabled by default.

- ``RUNMYCAMPUS_AI_ENABLED=1`` gates the North Star assistant layer.
- When enabled, prompts route through ``services.ai_gateway.invoke`` with
  ``allowed_backends`` defaulting to ollama + rules only unless
  ``RUNMYCAMPUS_AI_ALLOW_EXTERNAL=1``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from apps.platform_runtime.ai_governance import (
    read_tenant_ai_policy,
    resolve_allow_external_pii,
    resolve_effective_enabled,
    resolve_effective_external_network,
)


@runtime_checkable
class AIProvider(Protocol):
    """Minimal provider surface for future wiring (Ollama, HTTP gateway, etc.)."""

    code: str

    def is_configured(self) -> bool:
        ...

    def capabilities(self) -> dict[str, Any]:
        ...


@dataclass
class LocalOllamaStubProvider:
    """Placeholder for Ollama-style local inference (no network I/O here)."""

    code: str = "ollama_local"
    host: str = ""

    def is_configured(self) -> bool:
        return bool((self.host or "").strip())

    def capabilities(self) -> dict[str, Any]:
        return {"kind": "local", "model": "stub"}


@dataclass
class ExternalPlaceholderProvider:
    """Explicit external gateway placeholder — remains inert unless configured."""

    code: str = "external_placeholder"

    def is_configured(self) -> bool:
        return False

    def capabilities(self) -> dict[str, Any]:
        return {"kind": "external", "configured": False}


def get_ai_provider(school) -> dict[str, Any]:
    """
    Return tenant-scoped provider descriptor for the current school.

    Does not perform network I/O.
    """
    cfg = get_ai_runtime_config(school=school)
    code = "disabled"
    if cfg.get("enabled"):
        code = "ollama_local"
    sch_id = str(getattr(school, "pk", "") or "").strip()
    return {
        "code": code,
        "school_id": sch_id,
        **cfg,
        "external_network_allowed": cfg.get("external_network_allowed"),
    }


def run_ai_prompt(
    prompt: str,
    context: str,
    school,
    *,
    user=None,
    prompt_type: str = "generic",
    content_sensitivity: str = "standard",
) -> tuple[str, dict[str, Any]]:
    """
    Run a single assistant prompt through the AI gateway when North Star AI is enabled.

    When disabled, returns a safe local string and **does not** call the gateway
    (no inference, no outbound calls).

    Tenant isolation: ``school`` must match the active tenant; metadata includes
    ``school_id`` for gateway audit.
    """
    cfg = get_ai_runtime_config(school=school)
    if not cfg.get("enabled"):
        return (
            "AI assistant is disabled for this context. Enable RUNMYCAMPUS_AI_ENABLED "
            "and ensure the tenant has not disabled AI in School settings (ai_policy).",
            {
                "provider": "disabled",
                "northstar_ai_enabled": False,
                "prompt_type": prompt_type,
                "task_type": None,
            },
        )
    if school is None:
        return (
            "No school context is available for this assistant request.",
            {
                "provider": "disabled",
                "reason": "missing_school",
                "prompt_type": prompt_type,
            },
        )

    md: dict[str, Any] = {
        "school": school,
        "school_id": str(school.pk),
        "tenant_id": str(school.pk),
        "northstar_prompt_type": prompt_type,
    }
    if user is not None and getattr(user, "pk", None):
        md["user_id"] = user.pk
    ext_ok = bool(cfg.get("external_network_allowed"))
    high_pii = (content_sensitivity or "").strip().lower() in (
        "high_pii",
        "student_identifiers",
        "pii",
    )
    pii_ext_ok = bool(cfg.get("external_student_pii_allowed"))
    if not ext_ok or (high_pii and not pii_ext_ok):
        md["allowed_backends"] = ["ollama", "rules"]
    if ext_ok and high_pii and not pii_ext_ok:
        md["external_pii_blocked"] = True

    combined = (
        f"{prompt}\n\nAdditional context:\n{(context or '')[:8000]}"
    ).strip()
    user_query = (context or "")[:2000]

    try:
        from services.ai_gateway import TaskType, invoke

        result, meta = invoke(
            TaskType.NARRATIVE,
            combined,
            user_query=user_query,
            metadata=md,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            f"Assistant could not complete this request ({type(exc).__name__}).",
            {
                "provider": "error",
                "error": str(exc)[:200],
                "prompt_type": prompt_type,
            },
        )

    text = result if isinstance(result, str) else str(result or "")
    out = dict(meta) if isinstance(meta, dict) else {}
    out.setdefault("prompt_type", prompt_type)
    return text, out


def get_ai_runtime_config(
    *,
    site_settings: Any | None = None,
    school: Any | None = None,
) -> dict[str, Any]:
    """
    Return tenant-safe AI flags. See ``ai_governance`` for ``School.settings['ai_policy']``.
    """
    del site_settings  # reserved for SiteSettings-driven toggles (extend without breaking callers)

    enabled = resolve_effective_enabled(school=school)
    pol = read_tenant_ai_policy(school)
    ext_allowed = resolve_effective_external_network(school=school)
    pii_allowed = resolve_allow_external_pii(school=school)
    return {
        "enabled": enabled,
        "default_provider": "disabled",
        "local_provider": LocalOllamaStubProvider().capabilities(),
        "external_provider": ExternalPlaceholderProvider().capabilities(),
        "external_student_pii_allowed": pii_allowed,
        "external_network_allowed": ext_allowed,
        "audit_prompts_metadata": True,
        "tenant_opt_in_required": True,
        "tenant_ai_policy": pol,
    }


def describe_ai_assistant_surfaces() -> dict[str, str]:
    """Stable keys for CCC / dashboard / reports / onboarding entry points."""
    return {
        "config_copilot": "CCC / SiteConfig — structured setup guidance (draft only)",
        "report_comment_assistant": "Reports — narrative comments from non-identifying cues",
        "policy_assistant": "Policies — wording hints from tenant-safe excerpts",
        "workflow_builder_assistant": "Automation — workflow scaffolding (no execution)",
        "support_knowledge_assistant": "Support — internal KB-style hints (aggregates only by default)",
        "anomaly_nudge": "Health — anomaly / risk nudges from aggregated metrics",
        "school_health_insight": "Dashboard — school health narrative (approval required)",
        "onboarding_next_action": "Onboarding — next CCC step suggestion",
    }
