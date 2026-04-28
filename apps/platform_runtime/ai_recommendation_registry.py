"""
North Star AI recommendation registry.

Registry values are deterministic descriptors only; generation and execution remain
in dedicated services and always require explicit human approval.
"""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.ai_system_layer import (
    generate_anomaly_risk_nudge,
    generate_onboarding_next_action_insight,
    generate_school_health_insight,
    generate_workflow_suggestion,
)


AI_RECOMMENDATION_REGISTRY: dict[str, dict[str, Any]] = {
    "school_health": {
        "title": "School health insight",
        "generator": generate_school_health_insight,
        "approval_required": True,
        "category": "health",
    },
    "onboarding_next_action": {
        "title": "Onboarding next action",
        "generator": generate_onboarding_next_action_insight,
        "approval_required": True,
        "category": "onboarding",
    },
    "workflow_hygiene": {
        "title": "Workflow suggestion",
        "generator": generate_workflow_suggestion,
        "approval_required": True,
        "category": "automation",
    },
    "anomaly_risk": {
        "title": "Anomaly / risk nudge",
        "generator": generate_anomaly_risk_nudge,
        "approval_required": True,
        "category": "risk",
    },
}


def get_registered_ai_recommendations() -> dict[str, dict[str, Any]]:
    return dict(AI_RECOMMENDATION_REGISTRY)

