"""
First-class Trigger / Condition / Action registry for the workflow engine.
Tenant UI and automation can use this catalog to build or edit workflows (data-driven, tenant-configurable).
"""

from typing import Any

# Trigger types: when a workflow can run
TRIGGER_TYPES = {
    "scheduled": {
        "label": "Scheduled",
        "description": "Run on a schedule (cron/interval).",
        "config_schema": {"schedule": "cron_expr or interval"},
    },
    "event": {
        "label": "Event",
        "description": "Run when a domain event is emitted.",
        "config_schema": {"event_type": "string"},
    },
    "manual": {
        "label": "Manual",
        "description": "Run on demand via API or UI.",
        "config_schema": {},
    },
    "webhook": {
        "label": "Webhook",
        "description": "Run when an external webhook is received.",
        "config_schema": {"path": "string"},
    },
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
    "date_before": {"label": "Date before", "description": "Context date (ISO) is before value."},
    "date_after": {"label": "Date after", "description": "Context date (ISO) is after value."},
    "date_on_or_before": {
        "label": "Date on or before",
        "description": "Context date is on or before value.",
    },
    "date_on_or_after": {
        "label": "Date on or after",
        "description": "Context date is on or after value.",
    },
    "hour_between": {
        "label": "Hour between",
        "description": "Context datetime hour in [start, end] (0-23).",
    },
    "weekday_in": {
        "label": "Weekday in",
        "description": "Weekday in list (0=Monday ... 6=Sunday).",
    },
}

# School domain triggers (no-code builder + dispatch_domain_triggers)
SCHOOL_DOMAIN_TRIGGERS = {
    "student_updated": {
        "label": "Student updated",
        "description": "When a student profile is saved.",
    },
    "payment_received": {
        "label": "Payment received",
        "description": "When a payment or receipt is recorded.",
    },
    "grade_submitted": {
        "label": "Grade submitted",
        "description": "When an instructor submits or saves a grade.",
    },
    "attendance_marked": {
        "label": "Attendance marked",
        "description": "When attendance is recorded for a student.",
    },
    "report_published": {
        "label": "Report published",
        "description": "When a report card or term report is published.",
    },
}

# Action types: what the workflow can do (implementations in workflow_engine.run_actions)
ACTION_TYPES = {
    "notify": {
        "label": "Send notification",
        "description": "Notify user or role.",
        "params_schema": {"target": "user_id or role", "message": "string"},
    },
    "email": {
        "label": "Send email",
        "description": "Send an email to a recipient.",
        "params_schema": {"to": "email or role", "subject": "string", "body": "string"},
    },
    "log": {
        "label": "Log only",
        "description": "Audit log only, no side effect.",
        "params_schema": {"message": "string"},
    },
    "webhook": {
        "label": "Call webhook",
        "description": "POST to an external URL.",
        "params_schema": {"url": "string", "payload": "object"},
    },
    "emit_event": {
        "label": "Emit domain event",
        "description": "Emit an internal domain event.",
        "params_schema": {"event_type": "string", "payload": "object"},
    },
    "create_record": {
        "label": "Create record",
        "description": "Create an audited automation record (payload JSON).",
        "params_schema": {"record_type": "string", "payload": "object"},
    },
    "update_field": {
        "label": "Update field",
        "description": "Merge student_profile.custom_attributes (safe subset).",
        "params_schema": {
            "model_key": "student_profile",
            "field": "custom_attributes",
            "merge": "object",
        },
    },
    "ai_suggestion": {
        "label": "Run AI suggestion",
        "description": "Draft suggestion text (requires review before acting).",
        "params_schema": {"goal": "string", "include_context_keys": "list"},
    },
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
        "school_domain_triggers": dict(SCHOOL_DOMAIN_TRIGGERS),
        "condition_operators": get_condition_operators_catalog(),
        "action_types": get_action_types_catalog(),
    }
