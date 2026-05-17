"""Canonical notification template catalog — declarative SOT.

Like ``apps/marketplace/scopes_catalog.py``, this module is the
declarative inventory of every named notification template the
platform can render. Until a per-tenant override exists (in a future
migration), this catalog is the fallback.

Each entry has:
  * ``key``: stable identifier used by ``notification_service`` callers
  * ``channels``: which channels render this template (any of
    ``email``, ``sms``, ``whatsapp``, ``push``, ``in_app``)
  * ``audience``: who the template is for — guardian / student /
    staff / admin
  * ``subject_template``: short subject / push title (email + push)
  * ``body_template``: body text. Variables use ``{variable}`` style
    so the same string renders across channels; per-channel
    truncation is the caller's responsibility.
  * ``variables``: list of variable names available in the templates,
    so callers can validate context dicts before render.
  * ``sensitivity``: ``"low"`` / ``"medium"`` / ``"high"`` — controls
    redaction in audit logs.

This catalog is **read-only at runtime**. Per-tenant edits should land
in a future ``CommunicationTemplate`` model layered on top; see
``apps/communication/notification_service.py`` for the resolution
order (tenant override → this catalog → hard fallback).
"""

from __future__ import annotations


COMMUNICATION_TEMPLATES: dict[str, dict] = {
    # --- Attendance ---
    "attendance.absent_today": {
        "channels": ["sms", "whatsapp", "push", "in_app", "email"],
        "audience": "guardian",
        "subject_template": "Attendance update — {student_name}",
        "body_template": (
            "Hi {guardian_first_name}, {student_name} was marked absent today "
            "({absent_date}) at {school_name}. If this was unexpected, please "
            "contact the school office."
        ),
        "variables": ["guardian_first_name", "student_name", "absent_date", "school_name"],
        "sensitivity": "medium",
    },
    "attendance.late_today": {
        "channels": ["sms", "whatsapp", "in_app"],
        "audience": "guardian",
        "subject_template": "Late arrival — {student_name}",
        "body_template": (
            "{student_name} arrived late today ({arrival_time}) at {school_name}."
        ),
        "variables": ["student_name", "arrival_time", "school_name"],
        "sensitivity": "low",
    },
    "attendance.consecutive_absence_alert": {
        "channels": ["email", "push", "in_app"],
        "audience": "guardian",
        "subject_template": "Attendance concern — {student_name}",
        "body_template": (
            "{student_name} has been absent for {consecutive_days} consecutive "
            "school days. Please reply to acknowledge or contact the school "
            "office to discuss next steps."
        ),
        "variables": ["student_name", "consecutive_days"],
        "sensitivity": "medium",
    },
    # --- Academics ---
    "grades.published": {
        "channels": ["email", "in_app", "push"],
        "audience": "guardian",
        "subject_template": "Grades published — {term_name}",
        "body_template": (
            "Grades for {term_name} are now available in the parent portal. "
            "Sign in to view {student_name}'s report card."
        ),
        "variables": ["term_name", "student_name"],
        "sensitivity": "high",
    },
    "grades.at_risk_alert": {
        "channels": ["email", "in_app"],
        "audience": "staff",
        "subject_template": "Student at-risk: {student_name}",
        "body_template": (
            "The at-risk model flagged {student_name} (grade {grade_level}, "
            "{classroom_name}). Reasons: {reason_summary}."
        ),
        "variables": ["student_name", "grade_level", "classroom_name", "reason_summary"],
        "sensitivity": "high",
    },
    "evaluations.deadline_reminder": {
        "channels": ["email", "in_app", "push"],
        "audience": "staff",
        "subject_template": "Grade entry due — {subject_name} ({term_name})",
        "body_template": (
            "Reminder: {subject_name} grades for {term_name} are due by "
            "{deadline_date}. Please complete submissions in the gradebook."
        ),
        "variables": ["subject_name", "term_name", "deadline_date"],
        "sensitivity": "low",
    },
    # --- Finance ---
    "finance.invoice_issued": {
        "channels": ["email", "in_app", "push"],
        "audience": "guardian",
        "subject_template": "Invoice issued — {invoice_reference}",
        "body_template": (
            "Hi {guardian_first_name}, a new invoice for {amount} {currency} "
            "has been issued for {student_name}. Due date: {due_date}."
        ),
        "variables": ["guardian_first_name", "amount", "currency", "student_name", "due_date", "invoice_reference"],
        "sensitivity": "high",
    },
    "finance.payment_received": {
        "channels": ["email", "sms", "in_app"],
        "audience": "guardian",
        "subject_template": "Payment received — {amount} {currency}",
        "body_template": (
            "We've received your payment of {amount} {currency} for "
            "{student_name}. Reference: {payment_reference}. Thank you."
        ),
        "variables": ["amount", "currency", "student_name", "payment_reference"],
        "sensitivity": "high",
    },
    "finance.invoice_overdue": {
        "channels": ["email", "sms", "whatsapp", "in_app"],
        "audience": "guardian",
        "subject_template": "Overdue: {invoice_reference}",
        "body_template": (
            "Hi {guardian_first_name}, invoice {invoice_reference} for "
            "{student_name} is {days_overdue} days overdue ({balance} {currency}). "
            "Please contact the bursar if you need to discuss a payment plan."
        ),
        "variables": ["guardian_first_name", "invoice_reference", "student_name", "days_overdue", "balance", "currency"],
        "sensitivity": "high",
    },
    "finance.payment_plan_offered": {
        "channels": ["email", "in_app"],
        "audience": "guardian",
        "subject_template": "Payment plan available — {student_name}",
        "body_template": (
            "A payment plan has been proposed for {student_name}'s outstanding "
            "balance. Sign in to review and accept."
        ),
        "variables": ["student_name"],
        "sensitivity": "high",
    },
    # --- Admissions / Enrolment ---
    "admissions.application_received": {
        "channels": ["email", "in_app"],
        "audience": "guardian",
        "subject_template": "Application received — {applicant_name}",
        "body_template": (
            "We've received the application for {applicant_name}. Reference: "
            "{application_reference}. We'll follow up within {sla_days} days."
        ),
        "variables": ["applicant_name", "application_reference", "sla_days"],
        "sensitivity": "medium",
    },
    "admissions.interview_scheduled": {
        "channels": ["email", "sms", "in_app"],
        "audience": "guardian",
        "subject_template": "Interview scheduled — {applicant_name}",
        "body_template": (
            "An interview for {applicant_name} is scheduled for {interview_date} "
            "at {interview_time} at {location}."
        ),
        "variables": ["applicant_name", "interview_date", "interview_time", "location"],
        "sensitivity": "medium",
    },
    "admissions.offer_extended": {
        "channels": ["email", "in_app"],
        "audience": "guardian",
        "subject_template": "Offer of admission — {applicant_name}",
        "body_template": (
            "Congratulations — {applicant_name} has been offered admission. "
            "Please sign in to accept or decline by {response_deadline}."
        ),
        "variables": ["applicant_name", "response_deadline"],
        "sensitivity": "high",
    },
    "admissions.waitlist_notice": {
        "channels": ["email", "in_app"],
        "audience": "guardian",
        "subject_template": "Waitlisted — {applicant_name}",
        "body_template": (
            "{applicant_name} has been placed on the waitlist. We'll notify you "
            "if a place becomes available."
        ),
        "variables": ["applicant_name"],
        "sensitivity": "medium",
    },
    "enrolment.confirmed": {
        "channels": ["email", "in_app", "push"],
        "audience": "guardian",
        "subject_template": "Enrolment confirmed — {student_name}",
        "body_template": (
            "{student_name} is now enrolled for {term_name}. Classroom: "
            "{classroom_name}. Start date: {start_date}."
        ),
        "variables": ["student_name", "term_name", "classroom_name", "start_date"],
        "sensitivity": "medium",
    },
    # --- Compliance / DSAR ---
    "compliance.dsar_received": {
        "channels": ["email", "in_app"],
        "audience": "guardian",
        "subject_template": "Data request received — {request_reference}",
        "body_template": (
            "Your data subject access request ({request_reference}) has been "
            "received. We will respond within {sla_days} days as required by "
            "applicable data-protection law."
        ),
        "variables": ["request_reference", "sla_days"],
        "sensitivity": "high",
    },
    "compliance.consent_required": {
        "channels": ["email", "in_app", "push"],
        "audience": "guardian",
        "subject_template": "Consent required — {topic}",
        "body_template": (
            "Please review and provide consent for {topic} regarding "
            "{student_name}. Sign in to respond."
        ),
        "variables": ["topic", "student_name"],
        "sensitivity": "high",
    },
    # --- Safety / Emergency ---
    "emergency.school_closure": {
        "channels": ["sms", "whatsapp", "push", "in_app", "email", "voice"],
        "audience": "guardian",
        "subject_template": "URGENT: School closure — {school_name}",
        "body_template": (
            "{school_name} will be closed on {closure_date} due to {reason}. "
            "Updates will follow."
        ),
        "variables": ["school_name", "closure_date", "reason"],
        "sensitivity": "high",
    },
    "emergency.lockdown_drill": {
        "channels": ["push", "in_app", "email"],
        "audience": "staff",
        "subject_template": "Drill scheduled — {drill_type}",
        "body_template": (
            "A {drill_type} drill is scheduled at {school_name} on "
            "{drill_date} at {drill_time}. This is a drill — no action is "
            "required."
        ),
        "variables": ["drill_type", "school_name", "drill_date", "drill_time"],
        "sensitivity": "medium",
    },
    "emergency.weather_alert": {
        "channels": ["sms", "whatsapp", "push", "email"],
        "audience": "guardian",
        "subject_template": "Weather alert — {school_name}",
        "body_template": (
            "Due to {weather_event}, {school_name} will {action} on "
            "{effective_date}. Updates will follow."
        ),
        "variables": ["weather_event", "school_name", "action", "effective_date"],
        "sensitivity": "high",
    },
    # --- Transport ---
    "transport.bus_delay": {
        "channels": ["push", "in_app", "sms"],
        "audience": "guardian",
        "subject_template": "Bus delay — {route_name}",
        "body_template": (
            "Bus {route_name} is delayed by {delay_minutes} minutes. New ETA: "
            "{new_eta}."
        ),
        "variables": ["route_name", "delay_minutes", "new_eta"],
        "sensitivity": "low",
    },
    "transport.route_change": {
        "channels": ["email", "in_app", "push"],
        "audience": "guardian",
        "subject_template": "Route change — {route_name}",
        "body_template": (
            "Bus route {route_name} has been updated. New stops or times take "
            "effect on {effective_date}. Sign in to view the new plan."
        ),
        "variables": ["route_name", "effective_date"],
        "sensitivity": "low",
    },
    # --- Identity / Account ---
    "auth.password_reset": {
        "channels": ["email"],
        "audience": "any",
        "subject_template": "Password reset — {school_name}",
        "body_template": (
            "Hi {user_first_name}, click the link below to reset your password. "
            "This link expires in {expires_minutes} minutes.\n\n{reset_url}"
        ),
        "variables": ["user_first_name", "school_name", "expires_minutes", "reset_url"],
        "sensitivity": "high",
    },
    "auth.new_login_alert": {
        "channels": ["email", "push"],
        "audience": "any",
        "subject_template": "New sign-in from {device_label}",
        "body_template": (
            "Hi {user_first_name}, we noticed a sign-in to your account from "
            "{device_label} ({location}) at {when}. If this wasn't you, change "
            "your password immediately."
        ),
        "variables": ["user_first_name", "device_label", "location", "when"],
        "sensitivity": "high",
    },
    "auth.mfa_enabled": {
        "channels": ["email", "in_app"],
        "audience": "any",
        "subject_template": "MFA enabled",
        "body_template": (
            "Multi-factor authentication is now active on your account. If "
            "you didn't enable it, contact your school administrator."
        ),
        "variables": [],
        "sensitivity": "high",
    },
    # --- Operations ---
    "ops.report_ready": {
        "channels": ["email", "in_app"],
        "audience": "staff",
        "subject_template": "Report ready — {report_name}",
        "body_template": (
            "Your {report_name} export is ready. Sign in to download it."
        ),
        "variables": ["report_name"],
        "sensitivity": "medium",
    },
    "ops.workflow_pending_approval": {
        "channels": ["email", "in_app", "push"],
        "audience": "staff",
        "subject_template": "Approval pending — {workflow_name}",
        "body_template": (
            "A {workflow_name} request from {requester_name} is awaiting your "
            "approval."
        ),
        "variables": ["workflow_name", "requester_name"],
        "sensitivity": "medium",
    },
    "ops.workflow_approved": {
        "channels": ["email", "in_app", "push"],
        "audience": "any",
        "subject_template": "Approved — {workflow_name}",
        "body_template": (
            "Your {workflow_name} request has been approved by {approver_name}."
        ),
        "variables": ["workflow_name", "approver_name"],
        "sensitivity": "low",
    },
    "ops.workflow_rejected": {
        "channels": ["email", "in_app", "push"],
        "audience": "any",
        "subject_template": "Rejected — {workflow_name}",
        "body_template": (
            "Your {workflow_name} request was not approved. Reason: {reason}."
        ),
        "variables": ["workflow_name", "reason"],
        "sensitivity": "medium",
    },
}


def list_template_keys() -> list[str]:
    """Stable, sorted list of every template key. Useful for tests."""
    return sorted(COMMUNICATION_TEMPLATES.keys())


def get_template(key: str) -> dict | None:
    return COMMUNICATION_TEMPLATES.get(key)


def is_valid_key(key: str) -> bool:
    return key in COMMUNICATION_TEMPLATES


def templates_for_channel(channel: str) -> list[str]:
    """Return template keys whose channel list includes ``channel``."""
    return sorted(
        key for key, body in COMMUNICATION_TEMPLATES.items()
        if channel in body.get("channels", [])
    )


_HARD_FALLBACK = {
    "subject_template": "",
    "body_template": "(template missing)",
    "channels": [],
    "audience": "any",
    "sensitivity": "medium",
    "variables": [],
}


def resolve_template(key: str, *, school=None, locale: str = "") -> dict:
    """Resolve a template by precedence: tenant override → platform-wide
    DB override → code catalog → hard fallback.

    Returns a dict shaped like a catalog entry. Always safe to call —
    the hard fallback ensures notification_service never raises.

    Resolution avoids importing the model at module-import time so
    callers in non-Django contexts (tests, scripts) still work.
    """
    try:
        from apps.communication.models import CommunicationTemplate
    except Exception:  # noqa: BLE001 — Django not configured / migrations not run
        return get_template(key) or _hard_fallback_for(key)

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    qs = CommunicationTemplate.objects.filter(key=key, is_active=True)
    if locale:
        qs_for_locale = qs.filter(locale=locale)
        candidates = list(qs_for_locale) + list(qs.filter(locale=""))
    else:
        candidates = list(qs.filter(locale=""))

    school_id = getattr(school, "pk", None) if school is not None else None
    if school_id is not None:
        for row in candidates:
            if row.school_id == school_id:
                return _row_to_dict(row, key)
    for row in candidates:
        if row.school_id is None:
            return _row_to_dict(row, key)

    return get_template(key) or _hard_fallback_for(key)


def _row_to_dict(row, key: str) -> dict:
    catalog_entry = get_template(key) or {}
    channels = row.channels or catalog_entry.get("channels") or []
    return {
        "subject_template": row.subject_template or catalog_entry.get("subject_template", ""),
        "body_template": row.body_template,
        "channels": list(channels),
        "audience": row.audience or catalog_entry.get("audience", "any"),
        "sensitivity": row.sensitivity or catalog_entry.get("sensitivity", "medium"),
        "variables": catalog_entry.get("variables", []),
        "source": "db",
        "source_id": row.pk,
    }


def _hard_fallback_for(key: str) -> dict:
    out = dict(_HARD_FALLBACK)
    out["subject_template"] = key
    out["source"] = "hard_fallback"
    return out
