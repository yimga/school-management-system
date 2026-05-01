"""
Platform event catalog (Path-to-10). Formal event names and payload contracts
for automation, analytics, and orchestration. Emit via emit_platform_event().
All events carry tenant context; idempotency key optional for at-least-once safety.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from apps.platform_runtime.models import PlatformEventLog
from uuid import UUID

logger = logging.getLogger(__name__)

# Event catalog: event_type -> { description, payload_schema_hint }
EVENT_CATALOG = {
    "student_created": {
        "description": "Student record created",
        "payload": ["student_id", "school_id"],
    },
    "applicant_admitted": {
        "description": "Applicant admitted",
        "payload": ["applicant_id", "school_id"],
    },
    "attendance_marked": {
        "description": "Attendance marked for a session",
        "payload": ["attendance_id", "student_id", "school_id"],
    },
    "attendance_saved": {
        "description": "Attendance row persisted (platform bus + workflows + webhooks)",
        "payload": [
            "attendance_id",
            "student_id",
            "classroom_id",
            "school_id",
            "tenant_id",
            "status",
            "recorded_at",
            "event_id",
        ],
    },
    "platform_loop_attendance_trace": {
        "description": "Narrow loop proof: attendance_saved subscriber outcome (workflows + replay flags)",
        "payload": ["source_event_id", "school_id", "is_replay", "workflow_dispatch_ran"],
    },
    "platform_loop_webhook_outcome": {
        "description": "Loop proof: developer webhook delivery completed (attendance_saved fan-out)",
        "payload": [
            "platform_event_id",
            "delivery_id",
            "status",
            "latency_ms",
        ],
    },
    "grade_published": {
        "description": "Grades published",
        "payload": ["assessment_id", "school_id"],
    },
    "invoice_created": {
        "description": "Invoice created",
        "payload": ["invoice_id", "school_id"],
    },
    "payment_received": {
        "description": "Payment received",
        "payload": ["payment_id", "invoice_id", "school_id"],
    },
    "workflow_activated": {
        "description": "Workflow pack activated for tenant",
        "payload": ["workflow_pack_code", "school_id"],
    },
    "blueprint_applied": {
        "description": "Blueprint applied to tenant",
        "payload": ["blueprint_code", "school_id"],
    },
    "blueprint_rolled_back": {
        "description": "Tenant active blueprint bundle changed via control-plane rollback",
        "payload": [
            "school_id",
            "previous_bundle_id",
            "new_bundle_id",
            "actor_id",
        ],
    },
    "parent_notified": {
        "description": "Parent/guardian notified",
        "payload": ["notification_id", "school_id"],
    },
    "migration_started": {
        "description": "Migration job started",
        "payload": ["migration_id", "school_id"],
    },
    "migration_completed": {
        "description": "Migration job completed",
        "payload": ["migration_id", "school_id", "status"],
    },
    "package_applied": {
        "description": "Package applied (workflow/dashboard/policy)",
        "payload": ["package_id", "package_type", "school_id"],
    },
    "package_rolled_back": {
        "description": "Package rollback executed (metadata engine / tenant UI)",
        "payload": ["package_id", "version", "school_id", "actor_id"],
    },
    "nl_governed_query_executed": {
        "description": "BR-07 super governed data intent",
        "payload": ["intent", "user_id"],
    },
    "live_compliance_attendance": {
        "description": "BR-05 attendance validation flags",
        "payload": ["attendance_id", "issues", "school_id", "attendance_pack_key"],
    },
    "live_compliance_enrollment": {
        "description": "BR-05 degree enrollment validation flags",
        "payload": ["enrollment_id", "issues", "school_id", "enrollment_pack_key"],
    },
    "ews_intervention_started": {
        "description": "BR-06 intervention from at-risk UI",
        "payload": ["intervention_id", "student_id", "school_id"],
    },
    "provisioning_started": {
        "description": "Tenant provisioning job entered _do_provision (Tier 4 outbox)",
        "payload": ["school_id", "slug"],
    },
    "provisioning_completed": {
        "description": "Tenant provisioning finished successfully (school activated)",
        "payload": ["school_id", "slug"],
    },
    "learning_institution_packs_applied": {
        "description": "Delivery/institution learning packs merged into tenant settings/features",
        "payload": ["school_id", "delivery_wedges", "institution_wedge", "pack_slugs"],
    },
    "learning_wedge_pack_applied": {
        "description": "Single wedge pack slug applied (marketplace / one-click)",
        "payload": ["school_id", "pack_slug"],
    },
    "learning_wedge_pack_rolled_back": {
        "description": "Single learning wedge pack rolled back (tenant API)",
        "payload": ["school_id", "pack_slug", "actor_id", "features_cleared"],
    },
    "marketplace_app_installed": {
        "description": "Marketplace app installed (sandbox or active)",
        "payload": ["app_slug", "school_id", "install_phase"],
    },
    "tenant_surface_viewed": {
        "description": "Structured UI surface view (logging; see apps.platform_runtime.observability)",
        "payload": ["surface", "school_id", "user_id", "path"],
    },
    "celery_task_started": {
        "description": "Long-running Celery task entered",
        "payload": ["task_name", "celery_task_id", "school_id"],
    },
    "celery_task_completed": {
        "description": "Long-running Celery task finished successfully",
        "payload": ["task_name", "celery_task_id", "school_id"],
    },
    "celery_task_failed": {
        "description": "Long-running Celery task failed",
        "payload": ["task_name", "celery_task_id", "school_id", "error"],
    },
    "rum_web_vitals": {
        "description": "Client-reported Web Vitals / performance beacon (RUM)",
        "payload": ["path", "metrics", "navigation_type"],
    },
    "backlog_dependency_met": {
        "description": "Backlog unlock registry: automated criteria moved from waiting to ready/ready_attention",
        "payload": ["item_id", "title", "category", "display_status", "evaluation_profile"],
    },
    "fleet_governed_change_transitioned": {
        "description": "Fleet governed change (§2.1) status transition",
        "payload": [
            "change_id",
            "from_status",
            "to_status",
            "change_type",
            "actor_id",
            "error_message",
        ],
    },
    "fleet_governed_change_created": {
        "description": "Fleet governed change (§2.1) record created",
        "payload": [
            "change_id",
            "change_type",
            "status",
            "created_by_id",
            "title",
        ],
    },
    "support_desk_ticket_viewed": {
        "description": "Operator opened global support ticket detail (audit; no ticket body in payload)",
        "payload": ["ticket_id", "school_id", "actor_id"],
    },
    "support_desk_ticket_updated": {
        "description": "Operator updated ticket status and/or internal notes",
        "payload": ["ticket_id", "school_id", "actor_id", "changed_fields"],
    },
    "support_desk_ticket_assignment_changed": {
        "description": "Operator self-assigned or unassigned a global support ticket",
        "payload": ["ticket_id", "school_id", "actor_id", "action", "assignee_id"],
    },
    "support_desk_ticket_created": {
        "description": "Tenant user submitted a global support ticket (platform queue)",
        "payload": ["ticket_id", "school_id", "submitter_id", "priority", "status"],
    },
    "support_desk_ticket_reply_added": {
        "description": "Operator or submitter added a threaded reply on a global ticket",
        "payload": ["ticket_id", "school_id", "actor_id", "visibility"],
    },
    "support_desk_ticket_csat_submitted": {
        "description": "Submitter submitted CSAT (1–5) after resolution",
        "payload": ["ticket_id", "school_id", "actor_id", "score"],
    },
    "marks_submitted": {
        "description": "Teacher saved substantive marks on an evaluation row",
        "payload": [
            "evaluation_id",
            "student_id",
            "school_id",
            "subject_assignment_id",
            "term_id",
            "source",
        ],
    },
    "report_generated": {
        "description": "Report card PDF artifact persisted",
        "payload": ["report_card_id", "school_id", "student_id", "source"],
    },
    "payment_success": {
        "description": "Payment processor reported successful charge/settlement (platform bus)",
        "payload": ["school_id", "funnel_stage", "processor_source_ref"],
    },
    "payment_failed": {
        "description": "Payment processor reported failure (platform bus)",
        "payload": ["school_id", "funnel_stage", "processor_source_ref"],
    },
    "app_installed": {
        "description": "Marketplace app installed for tenant (workflow trigger alias)",
        "payload": ["app_slug", "school_id", "install_phase"],
    },
    "app_uninstalled": {
        "description": "Marketplace app marked uninstalled for tenant",
        "payload": ["app_slug", "school_id", "installation_id"],
    },
    "workflow_triggered": {
        "description": "Visual workflow executor started a live run",
        "payload": ["workflow_id", "trigger_event", "source"],
    },
    "workflow_completed": {
        "description": "Visual workflow run finished (success, failed, or skipped)",
        "payload": [
            "workflow_id",
            "workflow_run_log_id",
            "status",
            "trigger_event",
            "conditions_passed",
        ],
    },
    "offline_action_synced": {
        "description": "Durable OfflineAction reached SYNCED after server apply",
        "payload": ["offline_action_id", "action_type", "user_id", "source"],
    },
    "conversion_first_action": {
        "description": "Tenant completed first operational value action (conversion lock)",
        "payload": ["school_id", "source"],
    },
    "conversion_first_result": {
        "description": "Tenant recorded first funnel first_result milestone",
        "payload": ["school_id", "source"],
    },
    "platform_event_replayed": {
        "description": "Audit: subscribers/webhooks were re-invoked for an existing log row",
        "payload": [
            "source_event_id",
            "source_event_type",
            "dispatch_webhooks",
            "replayed_at",
        ],
    },
    "bus.test_ping": {
        "description": "Synthetic event for event-bus unit tests",
        "payload": ["msg"],
    },
}


def _json_safe_payload(obj: Any) -> Any:
    """Recursively coerce values so JSONField persistence never fails (UUID, Decimal, nested)."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {str(k): _json_safe_payload(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe_payload(x) for x in obj]
    try:
        return json.loads(json.dumps(obj, default=str))
    except (TypeError, ValueError):
        return str(obj)


def persist_platform_event(
    event_type: str,
    payload: Dict[str, Any],
    tenant_id: Optional[str] = None,
    school_id: Optional[Any] = None,
    idempotency_key: Optional[str] = None,
    *,
    require_catalog: bool = True,
) -> Optional["PlatformEventLog"]:
    """
    Append one platform event to the log (``PlatformEventLog`` / :class:`PlatformEvent`).

    When ``require_catalog`` is True, unknown ``event_type`` values are rejected.
    """
    if require_catalog and event_type not in EVENT_CATALOG:
        logger.warning("persist_platform_event: unknown event_type=%s", event_type)
        return None
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
    try:
        from apps.platform_runtime.models import PlatformEventLog

        clean = {k: v for k, v in payload.items() if not str(k).startswith("_")}
        return PlatformEventLog.objects.create(
            event_type=event_type[:64],
            payload=_json_safe_payload(clean),
            tenant_id=(str(tenant_id) if tenant_id is not None else "")[:64],
            school_id=(str(school_id) if school_id is not None else "")[:40],
            idempotency_key=(idempotency_key or "")[:128],
        )
    except Exception:
        logger.debug("PlatformEventLog persist skipped", exc_info=True)
        return None


def emit_platform_event(
    event_type: str,
    payload: Dict[str, Any],
    tenant_id: Optional[str] = None,
    school_id: Optional[Any] = None,
    idempotency_key: Optional[str] = None,
) -> Optional["PlatformEventLog"]:
    """
    Log-only emit (no pub/sub). For full fan-out use :func:`apps.platform_runtime.event_bus.publish_event`.
    """
    return persist_platform_event(
        event_type,
        payload,
        tenant_id=tenant_id,
        school_id=school_id,
        idempotency_key=idempotency_key,
        require_catalog=True,
    )


def get_event_catalog() -> Dict[str, Dict[str, Any]]:
    """Return the full event catalog for operator/API visibility."""
    return dict(EVENT_CATALOG)


def emit_celery_task_lifecycle(
    phase: str,
    task_name: str,
    *,
    celery_task_id: Optional[str] = None,
    school_id: Optional[Any] = None,
    error: Optional[str] = None,
) -> None:
    """Tier 4: started | completed | failed for async jobs (PlatformEventLog)."""
    mapping = {
        "started": "celery_task_started",
        "completed": "celery_task_completed",
        "failed": "celery_task_failed",
    }
    et = mapping.get(phase)
    if not et:
        return
    payload: Dict[str, Any] = {"task_name": task_name}
    if celery_task_id:
        payload["celery_task_id"] = str(celery_task_id)
    if school_id is not None:
        payload["school_id"] = str(school_id)
    if error:
        payload["error"] = str(error)[:2000]
    tid = str(school_id) if school_id is not None else None
    emit_platform_event(
        et,
        payload,
        tenant_id=tid,
        school_id=None,
        idempotency_key=f"{et}:{task_name}:{celery_task_id or ''}"[:120],
    )
