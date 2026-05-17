"""
Structured guided-assistant responses when live LLM tiers are unavailable.

Rules fallback must never return a plain string to guided endpoints — views expect a
validated guided_assistant dict with a non-empty summary when possible.
"""
from __future__ import annotations

from typing import Any

from services.ai_schemas import validate_guided_assistant

_OLLAMA_OPS_REF = "docs/OLLAMA_OPERATIONS_AND_UPDATES.md"

_TASK_HINTS: dict[str, str] = {
    "interop_assistant": (
        "District & LMS interop hub: /authentication/backend/district-lms-interop/. "
        "OneRoster at /api/oneroster/v1p1/; never paste district bearer tokens into chat."
    ),
    "studio_os_assistant": (
        "Studio OS on the manager host configures theme, experience, and automation rails. "
        "Use bounded consoles instead of raw Django admin when available."
    ),
    "observability_assistant": (
        "SLO dashboards and observability surfaces explain latency, errors, and tenant health. "
        "Check /super/ tenant health and trust center for fleet-wide signals."
    ),
    "billing_usage_explain": (
        "Billing usage and plan meters live under platform billing and finance modules. "
        "Usage meters roll up AI and marketplace consumption per tenant."
    ),
    "trust_compliance_assistant": (
        "Trust center and compliance audit logs document access, retention, and policy events. "
        "Prefer governed consoles over exporting raw audit tables."
    ),
    "runtime_config_explain": (
        "Runtime defaults and site settings cascade: env → RuntimeDefaults → SiteSettings → UI tokens."
    ),
    "control_plane_intelligence": (
        "Control plane dashboards summarize fleet posture: tenants, migration, marketplace, support."
    ),
    "setup_recommend": (
        "New schools should enable branding, academic year, roles, and data import before go-live."
    ),
    "config_explain": (
        "Configuration Control Center groups bounded settings domains; avoid scattered raw admin edits."
    ),
    "general_chat": "Ask about school operations, finance, academics, or compliance workflows.",
}


def _format_rag_snippets(rag_snippets: list[dict[str, Any]] | None) -> tuple[str, list[str]]:
    if not rag_snippets:
        return "", []
    lines: list[str] = []
    refs: list[str] = []
    for idx, item in enumerate(rag_snippets[:5], start=1):
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        scope = str(item.get("scope") or meta.get("scope") or "")[:32]
        title = (
            str(meta.get("title") or meta.get("source") or meta.get("policy") or f"snippet-{idx}")
        )[:120]
        body = str(item.get("text") or item.get("content") or meta.get("body") or "")[:400]
        if not body and meta:
            body = str(meta)[:400]
        if body:
            prefix = f"[{scope}] " if scope else ""
            lines.append(f"{prefix}{title}: {body}")
        ref = str(meta.get("url") or meta.get("path") or "").strip()
        if ref:
            refs.append(ref[:512])
    return "\n".join(lines), refs


def build_guided_fallback(
    *,
    task_type: str,
    user_query: str,
    rag_snippets: list[dict[str, Any]] | None = None,
    live_provider_available: bool = False,
) -> dict[str, Any]:
    """Return a validated guided_assistant payload for rules/degraded mode."""
    query = (user_query or "").strip()
    task_key = (task_type or "general_chat").strip().lower()
    hint = _TASK_HINTS.get(task_key) or _TASK_HINTS["general_chat"]
    rag_text, rag_refs = _format_rag_snippets(rag_snippets)

    summary_parts: list[str] = []
    if query:
        summary_parts.append(f"Question: {query[:500]}")
    if rag_text:
        summary_parts.append(
            "Retrieved platform context (no live model — answers are grounded on memory snippets only):"
        )
        summary_parts.append(rag_text[:2500])
    else:
        summary_parts.append(hint)

    if not live_provider_available:
        summary_parts.append(
            "Live AI provider is not connected. Configure Ollama (see "
            f"{_OLLAMA_OPS_REF}) for full model-generated answers."
        )

    actions: list[dict[str, str]] = []
    if query:
        actions.append(
            {
                "title": "Rephrase or narrow the question",
                "detail": "Ask about one surface (setup, billing, interop, Studio) at a time.",
            }
        )
    if not live_provider_available:
        actions.append(
            {
                "title": "Enable Ollama on the platform host",
                "detail": "Set OLLAMA endpoint and model in environment, then retry from AI Center.",
            }
        )

    cautions = [
        "Degraded mode: responses may omit tenant-specific details not present in retrieved memory.",
    ]
    if not live_provider_available:
        cautions.append("Do not paste secrets, API keys, or student PII into assistant prompts.")

    references = list(dict.fromkeys(rag_refs))[:10]
    if _OLLAMA_OPS_REF not in references and not live_provider_available:
        references.append(_OLLAMA_OPS_REF)

    payload = {
        "summary": "\n\n".join(p for p in summary_parts if p).strip(),
        "actions": actions,
        "cautions": cautions,
        "references": references,
    }
    if not payload["summary"]:
        payload["summary"] = (
            "AI assistant is in degraded mode. Connect a live provider or ask a more specific question."
        )
    return validate_guided_assistant(payload)
