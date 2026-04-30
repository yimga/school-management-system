"""
Code-backed event catalog: standard naming (domain.action), payload schemas, and audit.
Use emit_event() from apps.events.services only; event_type must be in EVENT_CATALOG when strict.
Master Platform Checklist §7.1, §7.2.
"""

from __future__ import annotations

# Event type -> {payload_required_keys, description, retry_policy, schema_version}
EVENT_CATALOG = {
    "student.created": {
        "payload_required_keys": ("student_id", "school_id"),
        "payload_optional_keys": ("admission_number",),
        "description": "Student profile created",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "student.updated": {
        "payload_required_keys": ("student_id", "school_id"),
        "payload_optional_keys": (),
        "description": "Student profile updated",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "applicant.admitted": {
        "payload_required_keys": ("applicant_id", "school_id"),
        "payload_optional_keys": ("student_id", "admission_number"),
        "description": "Applicant admitted; may have student_id if converted",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "attendance.recorded": {
        "payload_required_keys": ("school_id",),
        "payload_optional_keys": (
            "attendance_id",
            "teacher_attendance_id",
            "student_id",
            "teacher_id",
            "date",
            "status",
        ),
        "description": "Student or teacher attendance recorded",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "grade.published": {
        "payload_required_keys": ("school_id",),
        "payload_optional_keys": (
            "evaluation_id",
            "student_id",
            "term",
            "published_at",
        ),
        "description": "Grades published for a term/evaluation",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "invoice.created": {
        "payload_required_keys": ("invoice_id", "school_id"),
        "payload_optional_keys": ("student_id", "reference", "issued_date"),
        "description": "Invoice created",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "payment.received": {
        "payload_required_keys": ("payment_id", "school_id"),
        "payload_optional_keys": (
            "invoice_id",
            "student_id",
            "amount",
            "method",
            "reference",
        ),
        "description": "Payment recorded",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "workflow.triggered": {
        "payload_required_keys": (),
        "payload_optional_keys": ("workflow_key", "trigger", "context"),
        "description": "Workflow triggered (config-defined payload)",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "blueprint.applied": {
        "payload_required_keys": ("school_id",),
        "payload_optional_keys": ("blueprint_slug", "bundle_id", "applied_by"),
        "description": "Blueprint or policy bundle applied to tenant",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "parent.notified": {
        "payload_required_keys": ("school_id",),
        "payload_optional_keys": (
            "guardian_id",
            "student_id",
            "channel",
            "message_type",
        ),
        "description": "Parent/guardian notified",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "enrollment.created": {
        "payload_required_keys": ("enrollment_id", "student_id", "school_id"),
        "payload_optional_keys": ("program_id", "section_id"),
        "description": "Student enrolled in program/section",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "migration.started": {
        "payload_required_keys": ("school_id",),
        "payload_optional_keys": ("migration_run_id", "profile_slug", "triggered_by"),
        "description": "Migration run started",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
    "migration.completed": {
        "payload_required_keys": ("school_id",),
        "payload_optional_keys": (
            "migration_run_id",
            "status",
            "rows_created",
            "rows_updated",
            "error_count",
        ),
        "description": "Migration run completed",
        "retry_policy": "default",
        "schema_version": "1.0",
    },
}


def get_catalog() -> dict:
    """Return the full event catalog (read-only)."""
    return dict(EVENT_CATALOG)


def is_known_event_type(event_type: str) -> bool:
    """Return True if event_type is in the catalog."""
    return event_type in EVENT_CATALOG


def get_payload_required_keys(event_type: str) -> tuple:
    """Return required payload keys for event_type; empty if unknown."""
    entry = EVENT_CATALOG.get(event_type)
    if entry is None:
        return ()
    return entry.get("payload_required_keys", ())
