"""
Compliance alert utilities for real-time notifications and scheduled report delivery.
- Dispatch alerts for critical audit events via email/Slack/webhooks
- Provide escalation thresholds and runbook references
- Send scheduled compliance report emails
"""

import json
import logging
from urllib import request

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


def _should_alert(audit_log):
    cfg = getattr(settings, "COMPLIANCE_ALERTS", {})
    if not cfg.get("enabled", True):
        return False

    threshold = cfg.get("severity_threshold", "HIGH").upper()
    min_level = SEVERITY_ORDER.get(threshold, 3)
    severity_level = SEVERITY_ORDER.get((audit_log.sensitivity or "MEDIUM").upper(), 2)

    escalate_actions = {a.strip().upper() for a in cfg.get("escalate_on_actions", []) if a}
    action = (audit_log.action or "").upper()

    return severity_level >= min_level or action in escalate_actions


def _build_alert_message(audit_log):
    runbook_url = settings.COMPLIANCE_ALERTS.get("runbook_url") if hasattr(settings, "COMPLIANCE_ALERTS") else None
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


def _post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=5) as resp:  # nosec - trusted outbound webhook
        return resp.read()


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
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send compliance alert email: %s", exc)


def _send_slack(message: str):
    cfg = getattr(settings, "COMPLIANCE_ALERTS", {})
    webhook = cfg.get("slack_webhook_url")
    if not webhook:
        return
    payload = {"text": message}
    try:
        _post_json(webhook, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send Slack alert: %s", exc)


def _send_webhook(payload: dict):
    cfg = getattr(settings, "COMPLIANCE_ALERTS", {})
    webhook = cfg.get("generic_webhook_url")
    if not webhook:
        return
    try:
        _post_json(webhook, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send webhook alert: %s", exc)


def notify_audit_event(audit_log):
    """Dispatch alerts for qualifying audit events."""
    if not _should_alert(audit_log):
        return

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
        "runbook": settings.COMPLIANCE_ALERTS.get("runbook_url") if hasattr(settings, "COMPLIANCE_ALERTS") else None,
    }
    _send_webhook(structured)


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
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send compliance report email: %s", exc)
