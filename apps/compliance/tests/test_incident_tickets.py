"""
Integration tests for incident ticket creation.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.compliance.alerts import notify_audit_event, send_threat_alert
from apps.compliance.models_audit import AuditLog
from apps.observability.models import PlatformIncident

User = get_user_model()

_INCIDENT_RESPONSE_FULL = {
    "ticket_webhook": "https://example.com/create-ticket",
    "playbook_url": "https://example.com/playbook",
    "oncall_emails": ["oncall@example.com"],
}
_INCIDENT_RESPONSE_NO_ONCALL = {
    "ticket_webhook": "https://example.com/create-ticket",
    "playbook_url": "https://example.com/playbook",
    "oncall_emails": [],
}


class IncidentTicketIntegrationTestCase(TestCase):
    """Test incident ticket creation via webhooks."""

    def setUp(self):
        """Create test user."""
        cache.clear()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    @patch("apps.compliance.alerts._post_json")
    @override_settings(
        COMPLIANCE_ALERTS={
            "enabled": True,
            "email_recipients": [],
            "slack_webhook_url": "",
            "generic_webhook_url": "",
            "runbook_url": "https://example.com/runbook",
        },
        INCIDENT_RESPONSE=_INCIDENT_RESPONSE_FULL,
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_threat_alert_creates_ticket(self, mock_post_json):
        """Test that threat alerts trigger incident ticket creation."""
        # Create threat finding
        finding = {
            "type": "BRUTE_FORCE_USER",
            "user": "testuser",
            "ip_address": "192.168.1.100",
            "count": 15,
            "window": "60m",
            "severity": "HIGH",
            "description": "15 failed login attempts in 60 minutes",
        }

        # Send threat alert
        send_threat_alert(finding)

        # Verify ticket creation was attempted
        self.assertTrue(mock_post_json.called)

        # Find the call that was for ticket creation
        ticket_calls = [
            call
            for call in mock_post_json.call_args_list
            if "create-ticket" in str(call)
        ]
        self.assertEqual(len(ticket_calls), 1)

        # Verify ticket payload structure
        call_args = ticket_calls[0]
        ticket_payload = call_args[0][1]  # Second argument to _post_json

        self.assertIn("title", ticket_payload)
        self.assertIn("Threat Alert", ticket_payload["title"])
        self.assertEqual(ticket_payload["severity"], "HIGH")
        self.assertEqual(ticket_payload["type"], "threat.detection")
        self.assertEqual(ticket_payload["user"], "testuser")
        self.assertEqual(ticket_payload["ip_address"], "192.168.1.100")
        incident = PlatformIncident.objects.get(
            source_system="compliance.threat_detection"
        )
        self.assertEqual(incident.incident_type, PlatformIncident.IncidentType.SECURITY)
        self.assertEqual(incident.status, PlatformIncident.Status.OPEN)

    @patch("apps.compliance.alerts._post_json")
    @override_settings(
        COMPLIANCE_ALERTS={
            "enabled": True,
            "severity_threshold": "MEDIUM",
            "escalate_on_actions": [],
            "email_recipients": [],
            "slack_webhook_url": "",
            "generic_webhook_url": "",
            "runbook_url": "https://example.com/runbook",
        },
        INCIDENT_RESPONSE=_INCIDENT_RESPONSE_FULL,
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_high_severity_audit_creates_ticket(self, mock_post_json):
        """Test that HIGH/CRITICAL audit events trigger ticket creation."""
        # Create HIGH severity audit log
        audit_log = AuditLog.objects.create(
            action=AuditLog.Action.DELETE,
            model_name="Student",
            object_id="123",
            object_repr="John Doe",
            app_label="people",
            sensitivity=AuditLog.Sensitivity.HIGH,
            user=self.user,
            ip_address="192.168.1.1",
            reason="Manual deletion",
        )

        # Trigger alert
        notify_audit_event(audit_log)

        # Verify ticket creation was attempted
        ticket_calls = [
            call
            for call in mock_post_json.call_args_list
            if "create-ticket" in str(call)
        ]
        self.assertEqual(len(ticket_calls), 1)

        # Verify ticket payload
        ticket_payload = ticket_calls[0][0][1]
        self.assertIn("HIGH", ticket_payload["title"])
        self.assertEqual(ticket_payload["severity"], "HIGH")
        self.assertEqual(ticket_payload["type"], "compliance.audit")
        incident = PlatformIncident.objects.get(source_system="compliance.audit")
        self.assertEqual(incident.incident_type, PlatformIncident.IncidentType.SECURITY)
        self.assertEqual(incident.status, PlatformIncident.Status.OPEN)

    @patch("apps.compliance.alerts._post_json")
    @override_settings(
        COMPLIANCE_ALERTS={
            "enabled": True,
            "severity_threshold": "HIGH",
            "escalate_on_actions": [],
            "email_recipients": [],
            "slack_webhook_url": "",
            "generic_webhook_url": "",
            "runbook_url": "https://example.com/runbook",
        },
        INCIDENT_RESPONSE=_INCIDENT_RESPONSE_NO_ONCALL,
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_medium_severity_no_ticket(self, mock_post_json):
        """Test that MEDIUM severity audits don't create tickets."""
        # Create MEDIUM severity audit log
        audit_log = AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            model_name="Student",
            object_id="123",
            object_repr="John Doe",
            app_label="people",
            sensitivity=AuditLog.Sensitivity.MEDIUM,
            user=self.user,
            ip_address="192.168.1.1",
        )

        # Trigger alert
        notify_audit_event(audit_log)

        # Should not call _post_json for ticket creation
        # (may call for webhook, but not ticket_webhook)
        ticket_calls = [
            call
            for call in mock_post_json.call_args_list
            if "create-ticket" in str(call)
        ]
        self.assertEqual(len(ticket_calls), 0)
        self.assertFalse(
            PlatformIncident.objects.filter(source_system="compliance.audit").exists()
        )

    @patch("apps.compliance.alerts._post_json")
    @patch("apps.compliance.alerts.log_exception_with_context")
    @override_settings(
        COMPLIANCE_ALERTS={
            "enabled": True,
            "email_recipients": [],
            "slack_webhook_url": "",
            "generic_webhook_url": "",
            "runbook_url": "https://example.com/runbook",
        },
        INCIDENT_RESPONSE=_INCIDENT_RESPONSE_NO_ONCALL,
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_ticket_creation_failure_logged(self, mock_log_exc, mock_post_json):
        """Test that ticket creation failures are logged."""

        def _post_fail_ticket_webhook_only(webhook_url, *_args, **_kwargs):
            if "create-ticket" in str(webhook_url):
                raise RuntimeError("Network error")
            return None

        mock_post_json.side_effect = _post_fail_ticket_webhook_only

        finding = {
            "type": "BRUTE_FORCE_IP",
            "ip_address": "192.168.1.100",
            "count": 25,
            "window": "60m",
            "severity": "HIGH",
            "description": "Brute force detected",
        }

        send_threat_alert(finding)

        self.assertTrue(mock_log_exc.called)
        messages = [c[0][0] for c in mock_log_exc.call_args_list if c[0]]
        self.assertTrue(
            any("failed to create incident ticket" in str(m).lower() for m in messages),
            messages,
        )
