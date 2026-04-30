"""
North Star AI recommendation registry.

Each entry maps to a **real execution path** (URL chain per audience) consumed by
``action_engine._collect_ai_registry_actions``. Generators stay in ``ai_system_layer``;
this module only holds deterministic wiring — no empty or placeholder links.
"""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.ai_system_layer import (
    generate_anomaly_risk_nudge,
    generate_onboarding_next_action_insight,
    generate_school_health_insight,
    generate_workflow_suggestion,
)

# Keys: ``audiences`` uses "operator" for founder/admin/staff, or "teacher" / "parent" / "student", or "all".
# ``action_url_chains`` must resolve to at least one URL via Django reverse (first hit wins).
AI_RECOMMENDATION_REGISTRY: dict[str, dict[str, Any]] = {
    "school_health": {
        "title": "School health insight",
        "generator": generate_school_health_insight,
        "approval_required": True,
        "category": "health",
        "priority": 79,
        "urgency": "normal",
        "audiences": ("operator", "teacher", "parent", "student"),
        "action_url_chains": {
            "operator": (
                "siteconfig:dashboard_hub",
                "accounts:backend_dashboard",
                "analytics:dashboard",
            ),
            "teacher": (
                "portal:teacher_dashboard_alias",
                "portal:teacher_attendance",
                "evals:teacher_marks_entry",
            ),
            "parent": (
                "portal:parent_dashboard",
                "portal:parent_feed",
                "portal:parent_finance",
            ),
            "student": (
                "portal:student_portal_grades",
                "portal:unified_calendar",
            ),
        },
    },
    "onboarding_next_action": {
        "title": "Onboarding next action",
        "generator": generate_onboarding_next_action_insight,
        "approval_required": True,
        "category": "onboarding",
        "priority": 77,
        "urgency": "high",
        "audiences": ("operator", "teacher", "parent"),
        "action_url_chains": {
            "operator": (
                "siteconfig:dashboard_hub",
                "accounts:backend_dashboard",
            ),
            "teacher": (
                "portal:teacher_onboarding",
                "portal:teacher_dashboard_alias",
            ),
            "parent": (
                "portal:link_child",
                "portal:parent_dashboard",
            ),
        },
    },
    "workflow_hygiene": {
        "title": "Workflow suggestion",
        "generator": generate_workflow_suggestion,
        "approval_required": True,
        "category": "automation",
        "priority": 73,
        "urgency": "normal",
        "workflow_signal_key": "platform_strip",
        "audiences": ("operator", "teacher", "parent"),
        "action_url_chains": {
            "operator": (
                "studio_os:workflow_center",
                "siteconfig:workflow_flow_gallery",
                "siteconfig:guided_configuration_workflows",
            ),
            "teacher": (
                "evals:teacher_workflow",
                "portal:teacher_workflow",
                "portal:teacher_dashboard_alias",
            ),
            "parent": (
                "portal:parent_workflow",
                "portal:parent_dashboard",
            ),
        },
    },
    "anomaly_risk": {
        "title": "Anomaly / risk nudge",
        "generator": generate_anomaly_risk_nudge,
        "approval_required": True,
        "category": "risk",
        "priority": 81,
        "urgency": "high",
        "audiences": ("operator", "teacher", "parent"),
        "action_url_chains": {
            "operator": (
                "siteconfig:dashboard_hub",
                "analytics:dashboard",
                "accounts:backend_dashboard",
                "compliance:dashboard",
            ),
            "teacher": (
                "portal:teacher_attendance",
                "portal:teacher_dashboard_alias",
                "evals:teacher_dashboard",
            ),
            "parent": (
                "portal:parent_dashboard",
                "portal:parent_contact_school",
                "portal:parent_feed",
            ),
        },
    },
}


def get_registered_ai_recommendations() -> dict[str, dict[str, Any]]:
    return dict(AI_RECOMMENDATION_REGISTRY)
