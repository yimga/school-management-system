"""
Platform event catalog (Path-to-10). Formal event names and payload contracts
for automation, analytics, and orchestration. Emit via emit_platform_event().
All events carry tenant context; idempotency key optional for at-least-once safety.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Event catalog: event_type -> { description, payload_schema_hint }
EVENT_CATALOG = {
    "student_created": {"description": "Student record created", "payload": ["student_id", "school_id"]},
    "applicant_admitted": {"description": "Applicant admitted", "payload": ["applicant_id", "school_id"]},
    "attendance_marked": {"description": "Attendance marked for a session", "payload": ["attendance_id", "student_id", "school_id"]},
    "grade_published": {"description": "Grades published", "payload": ["assessment_id", "school_id"]},
    "invoice_created": {"description": "Invoice created", "payload": ["invoice_id", "school_id"]},
    "payment_received": {"description": "Payment received", "payload": ["payment_id", "invoice_id", "school_id"]},
    "workflow_activated": {"description": "Workflow pack activated for tenant", "payload": ["workflow_pack_code", "school_id"]},
    "blueprint_applied": {"description": "Blueprint applied to tenant", "payload": ["blueprint_code", "school_id"]},
    "parent_notified": {"description": "Parent/guardian notified", "payload": ["notification_id", "school_id"]},
    "migration_started": {"description": "Migration job started", "payload": ["migration_id", "school_id"]},
    "migration_completed": {"description": "Migration job completed", "payload": ["migration_id", "school_id", "status"]},
    "package_applied": {"description": "Package applied (workflow/dashboard/policy)", "payload": ["package_id", "package_type", "school_id"]},
    "package_rolled_back": {"description": "Package rollback executed", "payload": ["package_id", "school_id"]},
}


def emit_platform_event(
    event_type: str,
    payload: Dict[str, Any],
    tenant_id: Optional[str] = None,
    school_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> None:
    """
    Emit a platform event. Phase 1: log and catalog check; Phase 2: write to event store
    and fan-out to workflows/webhooks. All events must be in EVENT_CATALOG.
    """
    if event_type not in EVENT_CATALOG:
        logger.warning("emit_platform_event: unknown event_type=%s", event_type)
        return
    payload = dict(payload)
    if tenant_id is not None:
        payload["_tenant_id"] = tenant_id
    if school_id is not None:
        payload["_school_id"] = school_id
    if idempotency_key:
        payload["_idempotency_key"] = idempotency_key
    logger.info(
        "platform_event: type=%s tenant_id=%s school_id=%s idempotency_key=%s payload_keys=%s",
        event_type,
        tenant_id,
        school_id,
        idempotency_key,
        list(k for k in payload if not k.startswith("_")),
    )
    # Phase 2: persist to event store and trigger subscribers (workflows, webhooks, analytics).


def get_event_catalog() -> Dict[str, Dict[str, Any]]:
    """Return the full event catalog for operator/API visibility."""
    return dict(EVENT_CATALOG)
