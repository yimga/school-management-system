"""
First-class Trigger / Condition / Action registry for the workflow engine.
Tenant UI and automation can use this catalog to build or edit workflows (data-driven, tenant-configurable).
"""

from typing import Any

# Trigger types: when a workflow can run
TRIGGER_TYPES = {
    "scheduled": {"label": "Scheduled", "description": "Run on a schedule (cron/interval).", "config_schema": {"schedule": "cron_expr or interval"}},
    "event": {"label": "Event", "description": "Run when a domain event is emitted.", "config_schema": {"event_type": "string"}},
    "manual": {"label": "Manual", "description": "Run on demand via API or UI.", "config_schema": {}},
    "webhook": {"label": "Webhook", "description": "Run when an external webhook is received.", "config_schema": {"path": "string"}},
}

# Condition operators for evaluating context
CONDITION_OPERATORS = {
    "eq": {"label": "Equals", "description": "Field equals value."},
    "neq": {"label": "Not equals", "description": "Field does not equal value."},
    "gt": {"label": "Greater than", "description": "Numeric comparison."},
    "gte": {"label": "Greater or equal", "description": "Numeric comparison."},
    "lt": {"label": "Less than", "description": "Numeric comparison."},
    "lte": {"label": "Less or equal", "description": "Numeric comparison."},
    "in": {"label": "In list", "description": "Value is in the given list."},
    "contains": {"label": "Contains", "description": "String or list contains value."},
}

# Action types: what the workflow can do (implementations in workflow_engine.run_actions)
ACTION_TYPES = {
    "notify": {"label": "Send notification", "description": "Notify user or role.", "params_schema": {"target": "user_id or role", "message": "string"}},
    "email": {"label": "Send email", "description": "Send an email to a recipient.", "params_schema": {"to": "email or role", "subject": "string", "body": "string"}},
    "log": {"label": "Log only", "description": "Audit log only, no side effect.", "params_schema": {"message": "string"}},
    "webhook": {"label": "Call webhook", "description": "POST to an external URL.", "params_schema": {"url": "string", "payload": "object"}},
}


def get_trigger_catalog() -> dict[str, Any]:
    """Return catalog of trigger types for tenant UI."""
    return dict(TRIGGER_TYPES)


def get_condition_operators_catalog() -> dict[str, Any]:
    """Return catalog of condition operators."""
    return dict(CONDITION_OPERATORS)


def get_action_types_catalog() -> dict[str, Any]:
    """Return catalog of action types for tenant UI."""
    return dict(ACTION_TYPES)


def get_workflow_catalog() -> dict[str, Any]:
    """Return full catalog: triggers, condition_operators, action_types."""
    return {
        "triggers": get_trigger_catalog(),
        "condition_operators": get_condition_operators_catalog(),
        "action_types": get_action_types_catalog(),
    }
