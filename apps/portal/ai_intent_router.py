"""
Surface intent router (batch 1396 — unified AI gear 2).

Maps request path + role to a stable intent key consumed by gateway,
copilot, command bar, and MCP clients so every entry point shares one brain.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "SURFACE_INTENTS",
    "resolve_surface_intent",
    "intent_metadata",
]

SURFACE_INTENTS: frozenset[str] = frozenset(
    {
        "general_assistant",
        "help_kb",
        "workflow_playbook",
        "education_teacher",
        "education_parent",
        "migration_intake",
        "partner_interop",
        "module_inline",
        "operator_copilot",
        "risk_insights",
    }
)


def resolve_surface_intent(path: str, role: str = "") -> str:
    p = (path or "").lower()
    r = (role or "").upper()

    if "/education/teacher" in p:
        return "education_teacher"
    if "/education/parent" in p:
        return "education_parent"
    if "/partner-docs/" in p:
        return "partner_interop"
    if "/migration/" in p and ("intake" in p or "canonical" in p):
        return "migration_intake"
    if any(
        seg in p
        for seg in (
            "/onboarding",
            "/offboarding",
            "/school/studio",
            "/siteconfig/onboarding",
            "/authentication/backend/siteconfig/onboarding",
        )
    ):
        return "workflow_playbook"
    if "/help" in p or "/kb/" in p or "/feedback/help" in p:
        return "help_kb"
    if "/risk" in p or "/ai-surfaces/risk" in p:
        return "risk_insights"
    if any(
        seg in p
        for seg in (
            "/finance/",
            "/payroll/",
            "/evals/",
            "/attendance/",
            "/teacher/attendance",
            "/studio_os/",
        )
    ):
        return "module_inline"
    if r in {"ADMIN", "PROPRIETOR"} and (
        "manager." in p or "/super/" in p or "/siteconfig/super/" in p
    ):
        return "operator_copilot"
    if "/portal/guide" in p or "/guide/" in p:
        return "general_assistant"
    return "general_assistant"


def intent_metadata(intent: str) -> dict[str, Any]:
    """Static hints for UI chips — no secrets."""
    key = intent if intent in SURFACE_INTENTS else "general_assistant"
    labels = {
        "general_assistant": "RunMyCampus Guide",
        "help_kb": "Help & KB",
        "workflow_playbook": "Workflow playbook",
        "education_teacher": "Teacher education pack",
        "education_parent": "Family learning pack",
        "migration_intake": "Migration intake",
        "partner_interop": "Partner documentation",
        "module_inline": "Module assistant",
        "operator_copilot": "Operator copilot",
        "risk_insights": "Student risk insights",
    }
    return {
        "intent": key,
        "label": labels.get(key, labels["general_assistant"]),
        "grounded": key
        in {
            "help_kb",
            "workflow_playbook",
            "migration_intake",
            "partner_interop",
            "education_teacher",
            "education_parent",
        },
    }
