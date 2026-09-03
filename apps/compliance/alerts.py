"""
Compliance alert utilities for real-time notifications and scheduled report delivery.
- Dispatch alerts for critical audit events via email/Slack/webhooks
- Provide escalation thresholds and runbook references
- Send scheduled compliance report emails
§2.4: Typed exception tuples and structured logging (no broad except).
"""

import json
import logging
import smtplib
import time
from urllib import request, error as urllib_error

from django.conf import settings
from apps.schoolops.email_compat import send_mail
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

# §2.4: Typed tuples for compliance alert failure paths (allowlist 0).
_COMPLIANCE_ALERTS_EMAIL_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    smtplib.SMTPException,
    UnicodeError,
    AttributeError,
    TypeError,
    ValueError,
)
_COMPLIANCE_ALERTS_WEBHOOK_ERRORS = (
    urllib_error.HTTPError,
    urllib_error.URLError,
    TimeoutError,
    OSError,
    ConnectionError,
    ValueError,
    TypeError,
    RuntimeError,  # _post_json raises after retries exhausted
)
_COMPLIANCE_ALERTS_CACHE_PREFIX_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    LookupError,
    KeyError,
)
_COMPLIANCE_ALERTS_CACHE_BACKEND_ERRORS = (
    ConnectionError,
    ValueError,
    TypeError,
    AttributeError,
    RuntimeError,
)

SEVERITY_ORDER = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


def _platform_incident_severity(value: str):
    from apps.observability.models import PlatformIncident

    normalized = str(value or "MEDIUM").upper()
    mapping = {
        "LOW": PlatformIncident.Severity.LOW,
        "MEDIUM": PlatformIncident.Severity.MEDIUM,
        "HIGH": PlatformIncident.Severity.HIGH,
        "CRITICAL": PlatformIncident.Severity.CRITICAL,
    }
    return mapping.get(normalized, PlatformIncident.Severity.MEDIUM)


def _sync_platform_incident_from_audit_log(audit_log):
    from apps.observability.incident_services import upsert_platform_incident
    from apps.observability.models import PlatformIncident

    upsert_platform_incident(
        incident_key=f"audit:{audit_log.id}",
        title=f"Compliance audit escalation: {audit_log.model_name}",
        incident_type=PlatformIncident.IncidentType.SECURITY,
        severity=_platform_incident_severity(audit_log.sensitivity),
        summary=audit_log.summary,
        source_system="compliance.audit",
        details={
            "audit_log_id": audit_log.id,
            "action": audit_log.action,
            "model_name": audit_log.model_name,
            "object_id": audit_log.object_id,
            "ip_address": audit_log.ip_address,
            "reason": audit_log.reason,
        },
        created_by=audit_log.user,
    )


def _sync_platform_incident_from_threat(finding: dict):
    from apps.observability.incident_services import upsert_platform_incident
    from apps.observability.models import PlatformIncident

    threat_type = str(finding.get("type") or "unknown").strip().lower()
    incident_key = ":".join(
        [
            "threat",
            threat_type or "unknown",
            str(finding.get("user") or "system").strip().lower() or "system",
            str(finding.get("ip_address") or "unknown").strip().lower() or "unknown",
            str(finding.get("window") or "na").strip().lower() or "na",
        ]
    )
    upsert_platform_incident(
        incident_key=incident_key,
        title=f"Threat detected: {finding.get('type', 'Unknown')}",
        incident_type=PlatformIncident.IncidentType.SECURITY,
        severity=_platform_incident_severity(finding.get("severity")),
        summary=str(
            finding.get("description")
            or finding.get("type")
            or "Threat detection event"
        ),
        source_system="compliance.threat_detection",
        details={
            "threat_type": finding.get("type"),
            "user": finding.get("user"),
            "ip_address": finding.get("ip_address"),
            "count": finding.get("count"),
            "window": finding.get("window"),
        },
    )


def _should_alert(audit_log):
    cfg = getattr(settings, "COMPLIANCE_ALERTS", {})
    if not cfg.get("enabled", True):
        return False

    threshold = cfg.get("severity_threshold", "HIGH").upper()
    min_level = SEVERITY_ORDER.get(threshold, 3)
    severity_level = SEVERITY_ORDER.get((audit_log.sensitivity or "MEDIUM").upper(), 2)

    escalate_actions = {
        a.strip().upper() for a in cfg.get("escalate_on_actions", []) if a
    }
    action = (audit_log.action or "").upper()

    return severity_level >= min_level or action in escalate_actions


def _build_alert_message(audit_log):
    runbook_url = (
        settings.COMPLIANCE_ALERTS.get("runbook_url")
        if hasattr(settings, "COMPLIANCE_ALERTS")
        else None
    )
    user_label = audit_log.user.get_username() if audit_log.user else "System"
    return {
        "subject": f"[Compliance Alert] {audit_log.get_action_display()} {audit_log.model_name}",
        "text": (
            f"Action: {audit_log.get_action_display()}\n"
            f"Model: {audit_log.model_name}\n"
            f"Object: {audit_log.object_repr or audit_log.object_id}\n"
            f"Sensitivity: {audit_log.sensitivity}\n"
            f"User: {user_label}\n"
            f"IP: {audit_log.ip_address or 'N/A'}\n"
            f"When: {audit_log.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"Reason: {audit_log.reason or 'N/A'}\n"
            f"Runbook: {runbook_url or 'N/A'}\n"
        ),
    }


def _post_json(url, payload, max_retries=3):
    """
    POST JSON payload to URL with exponential backoff retry logic.

    Args:
        url: Target webhook URL
        payload: Dict to be JSON-encoded
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        Response body bytes on success

    Raises:
        Exception if all retries exhausted
    """
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})

    for attempt in range(max_retries):
        try:
            # Trusted outbound webhook. B310 is named deliberately: an
            # unscoped suppression waives EVERY check on this line, including
            # one that does not exist yet. (The marker below must carry test
            # ids only -- bandit reads any word after it as an id and warns.)
            with request.urlopen(req, timeout=5) as resp:  # nosec B310
                return resp.read()
        except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError) as exc:
            is_last_attempt = attempt == max_retries - 1

            if is_last_attempt:
                logger.error(
                    f"Webhook POST failed after {max_retries} attempts to {url}: {exc}"
                )
                raise

            # Exponential backoff: 2^attempt seconds (1s, 2s, 4s)
            backoff_seconds = 2**attempt
            logger.warning(
                f"Webhook POST attempt {attempt + 1}/{max_retries} failed to {url}: {exc}. "
                f"Retrying in {backoff_seconds}s..."
            )
            time.sleep(backoff_seconds)

    # Should never reach here due to raise in last attempt
    raise RuntimeError(f"Webhook POST failed after {max_retries} retries")


def _send_email(subject: str, message: str):
    cfg = getattr(settings, "COMPLIANCE_ALERTS", {})
    recipients = cfg.get("email_recipients", [])
    if not recipients:
        return
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=True,
        )
    except _COMPLIANCE_ALERTS_EMAIL_ERRORS as exc:
        log_exception_with_context(
            "compliance alert: failed to send email",
            school_id=None,
            extra={"subject": subject[:200], "error": str(exc)},
        )


def send_email_alert(subject: str, message: str):
    """
    Backwards-compatible public email sender for management commands.
    """
    _send_email(subject, message)


def _send_slack(message: str):
    cfg = getattr(settings, "COMPLIANCE_ALERTS", {})
    webhook = cfg.get("slack_webhook_url")
    if not webhook:
        return
    payload = {"text": message}
    try:
        _post_json(webhook, payload)
    except _COMPLIANCE_ALERTS_WEBHOOK_ERRORS as exc:
        log_exception_with_context(
            "compliance alert: failed to send Slack alert",
            school_id=None,
            extra={"error": str(exc)},
        )


def _send_webhook(payload: dict):
    cfg = getattr(settings, "COMPLIANCE_ALERTS", {})
    webhook = cfg.get("generic_webhook_url")
    if not webhook:
        return
    try:
        _post_json(webhook, payload)
    except _COMPLIANCE_ALERTS_WEBHOOK_ERRORS as exc:
        log_exception_with_context(
            "compliance alert: failed to send webhook alert",
            school_id=None,
            extra={"error": str(exc)},
        )


def _create_incident_ticket(payload: dict):
    """Create an incident ticket via webhook (e.g., Jira, PagerDuty, ServiceNow)."""
    incident_cfg = getattr(settings, "INCIDENT_RESPONSE", {})
    webhook = incident_cfg.get("ticket_webhook")
    if not webhook:
        return

    # Enrich payload with incident metadata
    ticket_payload = {
        "title": payload.get("title", "Security Incident"),
        "description": payload.get("description", ""),
        "severity": payload.get("severity", "MEDIUM"),
        "type": payload.get("type", "security.incident"),
        "occurred_at": payload.get("occurred_at"),
        "user": payload.get("user"),
        "ip_address": payload.get("ip_address"),
        "playbook_url": incident_cfg.get("playbook_url"),
        "oncall_emails": incident_cfg.get("oncall_emails", []),
        "metadata": payload.get("metadata", {}),
    }

    try:
        _post_json(webhook, ticket_payload)
        logger.info("Incident ticket created for: %s", payload.get("title"))
    except _COMPLIANCE_ALERTS_WEBHOOK_ERRORS as exc:
        log_exception_with_context(
            "compliance alert: failed to create incident ticket",
            school_id=None,
            extra={"title": payload.get("title", "")[:200], "error": str(exc)},
        )


from django.core.cache import cache


def notify_audit_event(audit_log):
    """Dispatch alerts for qualifying audit events. Use digest mode for LOW/MEDIUM severity.

    This function implements a short-lived dedupe using the cache to avoid duplicate
    alerts when the same audit event is processed multiple times in quick succession
    (e.g., created -> signal_handler -> manual call in tests).
    """
    # Include timestamp to prevent collisions when IDs are reused (e.g., test DB reset).
    event_ts = getattr(audit_log, "timestamp", None)
    ts_token = int(event_ts.timestamp()) if event_ts else "na"
    try:
        from apps.siteconfig.cache_utils import get_tenant_cache_prefix

        school_id = getattr(audit_log, "school_id", None)
        prefix = f"school:{school_id}" if school_id else get_tenant_cache_prefix()
    except _COMPLIANCE_ALERTS_CACHE_PREFIX_ERRORS:
        prefix = "public"
    dedupe_key = f"{prefix}:audit_alert_sent:{audit_log.id}:{ts_token}"
    # If already processed recently, skip to avoid duplicates
    try:
        if cache.get(dedupe_key):
            logger.debug("Skipping duplicate alert for audit_log %s", audit_log.id)
            return
    except _COMPLIANCE_ALERTS_CACHE_BACKEND_ERRORS:
        # If cache backend not available, proceed without dedupe
        pass

    if not _should_alert(audit_log):
        return

    severity = (audit_log.sensitivity or "MEDIUM").upper()

    # Use digest mode for LOW/MEDIUM severity
    if severity in ("LOW", "MEDIUM"):
        from apps.compliance.models_audit import AlertDigest

        AlertDigest.objects.create(
            alert_type=AlertDigest.AlertType.AUDIT,
            severity=severity,
            subject=f"{audit_log.get_action_display()} {audit_log.model_name}",
            message=_build_alert_message(audit_log)["text"],
            source="alerts.notify_audit_event",
            related_model=audit_log.model_name,
            related_id=audit_log.id,
        )
        logger.info(f"Added {severity} audit alert to digest: {audit_log}")
        # Mark as processed for a short time to avoid duplicates
        try:
            cache.set(dedupe_key, True, 60)
        except _COMPLIANCE_ALERTS_CACHE_BACKEND_ERRORS:
            pass
        return  # Don't send immediately

    # For HIGH/CRITICAL, send immediately
    message = _build_alert_message(audit_log)

    # Email
    _send_email(message["subject"], message["text"])

    # Slack (simple text)
    _send_slack(message["text"])

    # Generic webhook (structured JSON)
    structured = {
        "type": "compliance.alert",
        "occurred_at": audit_log.timestamp.isoformat(),
        "action": audit_log.action,
        "model": audit_log.model_name,
        "object_id": audit_log.object_id,
        "sensitivity": audit_log.sensitivity,
        "user": audit_log.user.get_username() if audit_log.user else "System",
        "ip_address": audit_log.ip_address,
        "reason": audit_log.reason,
        "runbook": settings.COMPLIANCE_ALERTS.get("runbook_url")
        if hasattr(settings, "COMPLIANCE_ALERTS")
        else None,
    }
    _send_webhook(structured)

    # Create incident ticket for HIGH/CRITICAL events (normalize TextChoices / DB value)
    if str(audit_log.sensitivity or "").upper() in ("HIGH", "CRITICAL"):
        _sync_platform_incident_from_audit_log(audit_log)
        _create_incident_ticket(
            {
                "title": f"[{audit_log.sensitivity}] {audit_log.get_action_display()} on {audit_log.model_name}",
                "description": message["text"],
                "severity": audit_log.sensitivity,
                "type": "compliance.audit",
                "occurred_at": audit_log.timestamp.isoformat(),
                "user": audit_log.user.get_username() if audit_log.user else "System",
                "ip_address": audit_log.ip_address,
                "metadata": {
                    "action": audit_log.action,
                    "model": audit_log.model_name,
                    "object_id": audit_log.object_id,
                },
            }
        )
        # Mark as processed for a short time to avoid duplicates
        try:
            cache.set(dedupe_key, True, 60)
        except _COMPLIANCE_ALERTS_CACHE_BACKEND_ERRORS:
            pass


def send_threat_alert(finding: dict):
    """Send threat detection alerts via configured channels."""
    cfg = getattr(settings, "COMPLIANCE_ALERTS", {})
    incident_cfg = getattr(settings, "INCIDENT_RESPONSE", {})
    if not cfg.get("enabled", True):
        return

    subject = f"[Threat Alert] {finding.get('type', 'Unknown')}"
    message = (
        f"Type: {finding.get('type')}\n"
        f"Severity: {finding.get('severity')}\n"
        f"User: {finding.get('user', 'N/A')}\n"
        f"IP: {finding.get('ip_address', 'N/A')}\n"
        f"Count: {finding.get('count', 'N/A')}\n"
        f"Window: {finding.get('window', 'N/A')}\n"
        f"Details: {finding.get('description', '')}\n"
        f"Playbook: {incident_cfg.get('playbook_url', 'N/A')}\n"
    )

    _send_email(subject, message)
    _send_slack(message)
    structured = {
        "type": "threat.alert",
        "severity": finding.get("severity"),
        "user": finding.get("user"),
        "ip_address": finding.get("ip_address"),
        "count": finding.get("count"),
        "window": finding.get("window"),
        "description": finding.get("description"),
        "runbook": cfg.get("runbook_url"),
    }
    _send_webhook(structured)
    _sync_platform_incident_from_threat(finding)

    # Create incident ticket for all threat alerts
    _create_incident_ticket(
        {
            "title": subject,
            "description": message,
            "severity": finding.get("severity", "HIGH"),
            "type": "threat.detection",
            "occurred_at": timezone.now().isoformat(),
            "user": finding.get("user"),
            "ip_address": finding.get("ip_address"),
            "metadata": {
                "threat_type": finding.get("type"),
                "count": finding.get("count"),
                "window": finding.get("window"),
            },
        }
    )


def send_compliance_report_email(reports):
    """Send scheduled compliance report summaries via email."""
    cfg = getattr(settings, "COMPLIANCE_ALERTS", {})
    if not cfg.get("report_email_enabled", True):
        return

    recipients = cfg.get("report_recipients", [])
    if not recipients:
        return

    lines = ["Compliance Reports", "===================", ""]
    for report in reports:
        lines.append(
            f"- {report.get_report_type_display()} ({report.start_date} to {report.end_date})"
        )
        lines.append(f"  Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"  Summary: {report.summary}")
        lines.append("")

    lines.append(f"Sent at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    runbook = cfg.get("runbook_url")
    if runbook:
        lines.append(f"Runbook: {runbook}")

    try:
        send_mail(
            subject="[Compliance] Scheduled Reports",
            message="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True,
        )
    except _COMPLIANCE_ALERTS_EMAIL_ERRORS as exc:
        log_exception_with_context(
            "compliance report: failed to send scheduled report email",
            school_id=None,
            extra={"error": str(exc)},
        )
