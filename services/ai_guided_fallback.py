"""
Structured guided-assistant responses when live LLM tiers are unavailable.

Degraded mode uses grounded retrieval (RAG snippets, topology, KB) to answer
concretely — not generic \"configure Ollama\" fluff.
"""
from __future__ import annotations

import re
from typing import Any

from services.ai_schemas import validate_guided_assistant

_OLLAMA_OPS_REF = "docs/OLLAMA_OPERATIONS_AND_UPDATES.md"

_TASK_HINTS: dict[str, str] = {
    "interop_assistant": (
        "District & LMS interop is under **Configure > District LMS interop** "
        "(path `/authentication/backend/district-lms-interop/`). "
        "OneRoster API: `/api/oneroster/v1p1/`. Never paste district bearer tokens into chat."
    ),
    "studio_os_assistant": (
        "Studio OS on the manager host configures theme rails, experience modes, and automation. "
        "Prefer Studio OS bounded consoles over raw Django admin for tenant branding."
    ),
    "observability_assistant": (
        "Check SLO and tenant health from control-plane observability surfaces and "
        "`/super/` tenant health dashboards when you need fleet-wide signals."
    ),
    "billing_usage_explain": (
        "Billing usage and plan meters live under platform billing and finance modules; "
        "meters roll up AI and marketplace consumption per tenant."
    ),
    "trust_compliance_assistant": (
        "Trust center and compliance audit logs document access, retention, and policy events. "
        "Use governed consoles instead of exporting raw audit tables."
    ),
    "runtime_config_explain": (
        "Runtime defaults cascade: environment → RuntimeDefaults → SiteSettings → portal tokens. "
        "Theme Experience Hub and Theme Builder are the bounded surfaces for visual config."
    ),
    "control_plane_intelligence": (
        "Control plane dashboards summarize fleet posture: tenants, migration cloud, marketplace, support."
    ),
    "setup_recommend": (
        "New schools on the manager host: use **Schools → Rapid Create** for a one-form tenant, "
        "or **Create school wizard** for staged provisioning. Track async jobs under **Provisioning jobs**."
    ),
    "config_explain": (
        "Configuration Control Center groups bounded settings domains; avoid scattered raw admin edits."
    ),
    "general_chat": (
        "Ask about one workflow at a time: admissions, finance, academics, interop, or compliance."
    ),
}

_QUERY_TOPICS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(add tenant|new tenant|create tenant|provision tenant|how can i add a tenant)\b", re.I),
        "setup_recommend",
    ),
    (re.compile(r"\b(tenant studio|create school|provision|wizard|rapid create)\b", re.I), "setup_recommend"),
    (re.compile(r"\b(studio os|theme builder|theme experience|branding|portal theme)\b", re.I), "studio_os_assistant"),
    (re.compile(r"\b(oneroster|interop|sis|lms|clever|classlink)\b", re.I), "interop_assistant"),
    (re.compile(r"\b(slo|observability|latency|metrics|health dashboard)\b", re.I), "observability_assistant"),
    (re.compile(r"\b(billing|invoice|usage meter|subscription plan)\b", re.I), "billing_usage_explain"),
    (re.compile(r"\b(ferpa|compliance|audit log|trust center|gdpr)\b", re.I), "trust_compliance_assistant"),
    (re.compile(r"\b(runtime default|site settings|cascade|feature flag)\b", re.I), "runtime_config_explain"),
)


def _infer_task_from_query(query: str, task_key: str, metadata: dict[str, Any] | None = None) -> str:
    key = (task_key or "general_chat").strip().lower()
    if key != "general_chat" and key in _TASK_HINTS:
        inferred = key
    else:
        inferred = key
        for pattern, topic in _QUERY_TOPICS:
            if pattern.search(query or ""):
                inferred = topic
                break
        if inferred not in _TASK_HINTS:
            inferred = key if key in _TASK_HINTS else "general_chat"

    perms = (metadata or {}).get("permissions")
    if isinstance(perms, dict):
        from services.ai_copilot_rbac import guided_task_allowed_for_permissions

        if not guided_task_allowed_for_permissions(inferred, perms):
            return "general_chat"
    return inferred


def _operator_provisioning_guidance(
    *,
    metadata: dict[str, Any] | None,
    query: str,
) -> tuple[str, list[dict[str, str]], list[str]]:
    """Concrete manager-host paths for tenant provisioning questions."""
    request = (metadata or {}).get("request")
    if request is None:
        return "", [], []
    if getattr(request, "public_host_kind", None) != "manager":
        return "", [], []
    perms = (metadata or {}).get("permissions")
    if not isinstance(perms, dict):
        return "", [], []
    if not perms.get("can_provision_tenants") and not perms.get("can_view_fleet_ops"):
        return "", [], []

    q = (query or "").lower()
    if not re.search(r"\b(tenant|school|provision|rapid create|add tenant|create school)\b", q):
        return "", [], []

    try:
        from django.urls import reverse

        rapid = reverse("super:schools_rapid_create")
        wizard = reverse("super:create_school_wizard")
        jobs = reverse("super:provisioning_jobs")
    except Exception:
        return "", [], []

    text = (
        "**Add a tenant on the manager host**\n"
        f"1. **Rapid Create** — `{rapid}` — fastest path: name, slug, country, optional template.\n"
        f"2. **Create school wizard** — `{wizard}` — staged provisioning with review checkpoints.\n"
        f"3. **Provisioning jobs** — `{jobs}` — monitor async migrations and seed tasks.\n"
        "After the tenant exists, open it from **Schools list** or use **Open as school** to finish Setup Studio."
    )
    actions = [
        {
            "title": "Open Rapid Create",
            "detail": f"One-form tenant provisioning — {rapid}",
        },
        {
            "title": "Open Create school wizard",
            "detail": f"Staged provisioning with checkpoints — {wizard}",
        },
        {
            "title": "View provisioning jobs",
            "detail": f"Track queued migrations — {jobs}",
        },
    ]
    return text, actions, [rapid, wizard, jobs]


def _format_rag_snippets(rag_snippets: list[dict[str, Any]] | None) -> tuple[str, list[str], list[dict[str, str]]]:
    if not rag_snippets:
        return "", [], []
    lines: list[str] = []
    refs: list[str] = []
    actions: list[dict[str, str]] = []
    for idx, item in enumerate(rag_snippets[:6], start=1):
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        scope = str(item.get("scope") or meta.get("scope") or "")[:32]
        title = (
            str(meta.get("title") or meta.get("source") or meta.get("policy") or f"snippet-{idx}")
        )[:120]
        body = str(item.get("text") or item.get("content") or meta.get("text") or meta.get("body") or "")[:500]
        if not body and meta:
            body = str(meta)[:500]
        if body:
            prefix = f"[{scope}] " if scope else ""
            lines.append(f"{prefix}{title}: {body}")
            actions.append({"title": title[:80], "detail": body[:400]})
        ref = str(meta.get("url") or meta.get("path") or "").strip()
        if ref:
            refs.append(ref[:512])
    return "\n".join(lines), refs, actions


def _topology_guidance(
    *,
    metadata: dict[str, Any] | None,
    query: str,
) -> tuple[str, list[dict[str, str]], list[str]]:
    """Permission-aware nav matches from SYSTEM_TOPOLOGY_MAP."""
    request = (metadata or {}).get("request")
    if request is None or not (query or "").strip():
        return "", [], []
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return "", [], []
    school = (metadata or {}).get("school") or getattr(request, "school", None)
    try:
        from services.ai.topology_map import search_topology

        hits = search_topology(user, query, school=school, limit=4)
    except Exception:
        return "", [], []

    lines: list[str] = []
    actions: list[dict[str, str]] = []
    refs: list[str] = []
    for row in hits:
        if row.get("locked"):
            continue
        label = str(row.get("label") or "").strip()
        path_label = str(row.get("path_label") or "").strip()
        url = row.get("url")
        if not label:
            continue
        detail = path_label or label
        if url:
            detail = f"{detail} — open {url}"
            refs.append(str(url)[:512])
        lines.append(f"• {label}: {path_label or 'see linked surface'}")
        actions.append({"title": f"Open {label}", "detail": detail[:400]})
    if not lines:
        return "", [], []
    return "\n".join(lines), actions, refs


def _extra_knowledge(
    *,
    metadata: dict[str, Any] | None,
    query: str,
    task_key: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Pull KB / vector snippets when the view did not attach rag_snippets."""
    request = (metadata or {}).get("request")
    if request is None:
        return [], []
    user = getattr(request, "user", None)
    school = (metadata or {}).get("school") or getattr(request, "school", None)
    try:
        from services.ai.tenant_isolation import TenantContextEnforcer
        from services.ai.knowledge import retrieve_knowledge_snippets

        enforcer = TenantContextEnforcer(user, school=school)
        scope = enforcer.resolve_scope().tier
    except Exception:
        scope = None
    if scope is None:
        return [], []
    try:
        lines, rows = retrieve_knowledge_snippets(
            user=user,
            school=school,
            user_query=query,
            scope=scope,
            limit=4,
        )
        return lines, rows
    except Exception:
        return [], []


def _compose_summary(
    *,
    query: str,
    task_key: str,
    hint: str,
    rag_text: str,
    topology_text: str,
    live_provider_available: bool,
) -> str:
    parts: list[str] = []

    if rag_text or topology_text:
        if query:
            parts.append(f"For your question about “{query[:200]}”:")
        else:
            parts.append("Here is what the platform knowledge base suggests:")
        if topology_text:
            parts.append("**Where to go in the product**\n" + topology_text)
        if rag_text:
            parts.append("**Grounded details**\n" + rag_text[:2200])
    else:
        parts.append(hint)
        if query:
            parts.append(
                f"You asked: “{query[:300]}”. "
                "No matching help articles were retrieved — use the steps below or narrow to one surface."
            )

    if not live_provider_available:
        parts.append(
            "_Note: the language model on this server is offline; this answer is assembled from "
            "product maps and retrieved documentation only._"
        )
    return "\n\n".join(p for p in parts if p).strip()


def build_guided_fallback(
    *,
    task_type: str,
    user_query: str,
    rag_snippets: list[dict[str, Any]] | None = None,
    live_provider_available: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a validated guided_assistant payload for rules/degraded mode."""
    query = (user_query or "").strip()
    task_key = _infer_task_from_query(query, (task_type or "general_chat").strip().lower(), metadata)
    hint = _TASK_HINTS.get(task_key) or _TASK_HINTS["general_chat"]

    rag_text, rag_refs, rag_actions = _format_rag_snippets(rag_snippets)
    extra_lines, extra_rows = _extra_knowledge(metadata=metadata, query=query, task_key=task_key)
    if extra_lines and not rag_text:
        rag_text = "\n".join(extra_lines)[:2200]
        rag_snippets = (rag_snippets or []) + list(extra_rows)

    topology_text, topo_actions, topo_refs = _topology_guidance(metadata=metadata, query=query)
    provision_text, provision_actions, provision_refs = _operator_provisioning_guidance(
        metadata=metadata,
        query=query,
    )
    if provision_text:
        if topology_text:
            topology_text = provision_text + "\n\n" + topology_text
        else:
            topology_text = provision_text
        topo_actions = provision_actions + topo_actions
        topo_refs = list(dict.fromkeys(provision_refs + topo_refs))

    summary = _compose_summary(
        query=query,
        task_key=task_key,
        hint=hint,
        rag_text=rag_text,
        topology_text=topology_text,
        live_provider_available=live_provider_available,
    )

    actions: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    for row in topo_actions + rag_actions:
        title = str(row.get("title") or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        actions.append(row)
    if not actions and query:
        actions.append(
            {
                "title": "Narrow the question",
                "detail": "Ask about one surface (setup, billing, interop, Studio, theme) at a time.",
            }
        )

    cautions = [
        "Grounded mode: verify tenant-specific numbers and permissions in the live UI before acting.",
    ]
    if not live_provider_available:
        cautions.append(
            "Language model offline on this host — steps come from maps and KB, not generative reasoning."
        )

    references = list(dict.fromkeys(topo_refs + rag_refs))[:10]
    if not live_provider_available and _OLLAMA_OPS_REF not in references:
        references.append(_OLLAMA_OPS_REF)

    payload = {
        "summary": summary,
        "actions": actions[:6],
        "cautions": cautions,
        "references": references,
    }
    if not payload["summary"]:
        payload["summary"] = hint
    return validate_guided_assistant(payload)
