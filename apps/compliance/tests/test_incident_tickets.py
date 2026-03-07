"""
Integration tests for incident ticket creation.
"""
import unittest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.compliance.models_audit import AuditLog
from apps.compliance.alerts import send_threat_alert, notify_audit_event
from apps.observability.models import PlatformIncident

User = get_user_model()


class IncidentTicketIntegrationTestCase(TestCase):
    """Test incident ticket creation via webhooks."""

    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    @patch('apps.compliance.alerts._post_json')
    @patch('apps.compliance.alerts.settings')
    def test_threat_alert_creates_ticket(self, mock_settings, mock_post_json):
        """Test that threat alerts trigger incident ticket creation."""
        # Mock settings
        mock_settings.COMPLIANCE_ALERTS = {
            'enabled': True,
            'email_recipients': [],
            'slack_webhook_url': '',
            'generic_webhook_url': '',
            'runbook_url': 'https://example.com/runbook'
        }
        mock_settings.INCIDENT_RESPONSE = {
            'ticket_webhook': 'https://example.com/create-ticket',
            'playbook_url': 'https://example.com/playbook',
            'oncall_emails': ['oncall@example.com']
        }
        mock_settings.DEFAULT_FROM_EMAIL = 'noreply@example.com'
        
        # Create threat finding
        finding = {
            'type': 'BRUTE_FORCE_USER',
            'user': 'testuser',
            'ip_address': '192.168.1.100',
            'count': 15,
            'window': '60m',
            'severity': 'HIGH',
            'description': '15 failed login attempts in 60 minutes'
        }
        
        # Send threat alert
        send_threat_alert(finding)
        
        # Verify ticket creation was attempted
        self.assertTrue(mock_post_json.called)
        
        # Find the call that was for ticket creation
        ticket_calls = [
            call for call in mock_post_json.call_args_list
            if 'create-ticket' in str(call)
        ]
        self.assertEqual(len(ticket_calls), 1)
        
        # Verify ticket payload structure
        call_args = ticket_calls[0]
        ticket_payload = call_args[0][1]  # Second argument to _post_json
        
        self.assertIn('title', ticket_payload)
        self.assertIn('Threat Alert', ticket_payload['title'])
        self.assertEqual(ticket_payload['severity'], 'HIGH')
        self.assertEqual(ticket_payload['type'], 'threat.detection')
        self.assertEqual(ticket_payload['user'], 'testuser')
        self.assertEqual(ticket_payload['ip_address'], '192.168.1.100')
        incident = PlatformIncident.objects.get(source_system="compliance.threat_detection")
        self.assertEqual(incident.incident_type, PlatformIncident.IncidentType.SECURITY)
        self.assertEqual(incident.status, PlatformIncident.Status.OPEN)

    @patch('apps.compliance.alerts._post_json')
    @patch('apps.compliance.alerts.settings')
    def test_high_severity_audit_creates_ticket(self, mock_settings, mock_post_json):
        """Test that HIGH/CRITICAL audit events trigger ticket creation."""
        # Mock settings
        mock_settings.COMPLIANCE_ALERTS = {
            'enabled': True,
            'severity_threshold': 'MEDIUM',
            'escalate_on_actions': [],
            'email_recipients': [],
            'slack_webhook_url': '',
            'generic_webhook_url': '',
            'runbook_url': 'https://example.com/runbook'
        }
        mock_settings.INCIDENT_RESPONSE = {
            'ticket_webhook': 'https://example.com/create-ticket',
            'playbook_url': 'https://example.com/playbook',
            'oncall_emails': ['oncall@example.com']
        }
        mock_settings.DEFAULT_FROM_EMAIL = 'noreply@example.com'
        
        # Create HIGH severity audit log
        audit_log = AuditLog.objects.create(
            action=AuditLog.Action.DELETE,
            model_name='Student',
            object_id='123',
            object_repr='John Doe',
            app_label='people',
            sensitivity=AuditLog.Sensitivity.HIGH,
            user=self.user,
            ip_address='192.168.1.1',
            reason='Manual deletion'
        )
        
        # Trigger alert
        notify_audit_event(audit_log)
        
        # Verify ticket creation was attempted
        ticket_calls = [
            call for call in mock_post_json.call_args_list
            if 'create-ticket' in str(call)
        ]
        self.assertEqual(len(ticket_calls), 1)
        
        # Verify ticket payload
        ticket_payload = ticket_calls[0][0][1]
        self.assertIn('HIGH', ticket_payload['title'])
        self.assertEqual(ticket_payload['severity'], 'HIGH')
        self.assertEqual(ticket_payload['type'], 'compliance.audit')
        incident = PlatformIncident.objects.get(source_system="compliance.audit")
        self.assertEqual(incident.incident_type, PlatformIncident.IncidentType.SECURITY)
        self.assertEqual(incident.status, PlatformIncident.Status.OPEN)

    @patch('apps.compliance.alerts._post_json')
    @patch('apps.compliance.alerts.settings')
    def test_medium_severity_no_ticket(self, mock_settings, mock_post_json):
        """Test that MEDIUM severity audits don't create tickets."""
        # Mock settings
        mock_settings.COMPLIANCE_ALERTS = {
            'enabled': True,
            'severity_threshold': 'HIGH',
            'escalate_on_actions': [],
            'email_recipients': [],
            'slack_webhook_url': '',
            'generic_webhook_url': '',
            'runbook_url': 'https://example.com/runbook'
        }
        mock_settings.INCIDENT_RESPONSE = {
            'ticket_webhook': 'https://example.com/create-ticket',
            'playbook_url': 'https://example.com/playbook',
            'oncall_emails': []
        }
        mock_settings.DEFAULT_FROM_EMAIL = 'noreply@example.com'
        
        # Create MEDIUM severity audit log
        audit_log = AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            model_name='Student',
            object_id='123',
            object_repr='John Doe',
            app_label='people',
            sensitivity=AuditLog.Sensitivity.MEDIUM,
            user=self.user,
            ip_address='192.168.1.1'
        )
        
        # Trigger alert
        notify_audit_event(audit_log)
        
        # Should not call _post_json for ticket creation
        # (may call for webhook, but not ticket_webhook)
        ticket_calls = [
            call for call in mock_post_json.call_args_list
            if 'create-ticket' in str(call)
        ]
        self.assertEqual(len(ticket_calls), 0)
        self.assertFalse(PlatformIncident.objects.filter(source_system="compliance.audit").exists())

    @patch('apps.compliance.alerts._post_json')
    @patch('apps.compliance.alerts.logger')
    @patch('apps.compliance.alerts.settings')
    def test_ticket_creation_failure_logged(self, mock_settings, mock_logger, mock_post_json):
        """Test that ticket creation failures are logged."""
        # Mock settings
        mock_settings.COMPLIANCE_ALERTS = {
            'enabled': True,
            'email_recipients': [],
            'slack_webhook_url': '',
            'generic_webhook_url': '',
            'runbook_url': 'https://example.com/runbook'
        }
        mock_settings.INCIDENT_RESPONSE = {
            'ticket_webhook': 'https://example.com/create-ticket',
            'playbook_url': 'https://example.com/playbook',
            'oncall_emails': []
        }
        mock_settings.DEFAULT_FROM_EMAIL = 'noreply@example.com'
        
        # Make _post_json raise an exception
        mock_post_json.side_effect = Exception("Network error")
        
        # Create threat finding
        finding = {
            'type': 'BRUTE_FORCE_IP',
            'ip_address': '192.168.1.100',
            'count': 25,
            'window': '60m',
            'severity': 'HIGH',
            'description': 'Brute force detected'
        }
        
        # Send threat alert - should not raise exception
        send_threat_alert(finding)
        
        # Verify warning was logged
        self.assertTrue(mock_logger.warning.called)
        warning_message = str(mock_logger.warning.call_args)
        self.assertIn("Failed to create incident ticket", warning_message)
