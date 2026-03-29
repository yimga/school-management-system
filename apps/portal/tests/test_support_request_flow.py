"""End-to-end portal support_request: GlobalSupportTicket, Message, metadata, optional AI triage."""

from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.communication.models import Message
from apps.portal.tasks import apply_support_ticket_ai_triage
from apps.portal.views_support import support_request
from apps.schools.models import School
from apps.siteconfig.models_feature_controls import GlobalSupportTicket


def _sessioned_request(rf, user, school, path, post_data):
    request = rf.post(path, data=post_data)
    request.user = user
    request.school = school
    SessionMiddleware(lambda r: HttpResponse()).process_request(request)
    request.session.save()
    setattr(request, "_messages", FallbackStorage(request))
    return request


class SupportRequestFlowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Flow School",
            slug="flow-school",
            subdomain="flow-school",
            is_active=True,
        )
        self.sender = User.objects.create_user(
            username="flow-sender",
            password="pass",
            role=User.Role.ADMIN,
            email="sender@example.com",
        )
        User.objects.create_user(
            username="flow-it",
            password="pass",
            role=User.Role.IT_ADMIN,
            email="it@example.com",
        )

    def test_get_renders_with_resilient_edge_wrappers(self):
        rf = RequestFactory()
        path = reverse("portal:support_request")
        request = rf.get(path)
        request.user = self.sender
        request.school = self.school
        SessionMiddleware(lambda r: HttpResponse()).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        response = support_request(request)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('data-page-archetype="support-request"', body)
        self.assertIn('data-sms-offline-read-cache-key="portal_support_request"', body)

    @override_settings(
        SUPPORT_AI_AUTO_TRIAGE_ON_CREATE=True,
        AI_GATEWAY_ENABLED=True,
        SUPPORT_TICKET_NOTIFY_EMAIL=False,
        SUPPORT_TICKET_NOTIFY_INAPP=False,
    )
    @patch("apps.portal.tasks.apply_support_ticket_ai_triage.delay")
    @patch("apps.portal.runtime_helpers.get_policy_for_request")
    @patch("services.ai_gateway.invoke")
    def test_post_creates_ticket_message_and_triage_metadata(
        self, mock_invoke, mock_policy, mock_delay
    ):
        mock_policy.return_value = {"plan_slug": "pro", "country_code": "CM"}
        mock_invoke.return_value = (
            '{"category":"ACCESS","priority":"NORMAL","suggested_reply":"Reset link."}',
            {"gateway": True},
        )
        mock_delay.side_effect = lambda pk: apply_support_ticket_ai_triage(str(pk))
        rf = RequestFactory()
        path = reverse("portal:support_request")
        data = {
            "category": "SUPPORT",
            "subject": "Cannot log in",
            "message": "Portal shows error 500 after login.",
        }
        request = _sessioned_request(rf, self.sender, self.school, path, data)
        with patch(
            "apps.portal.views_support.transaction.on_commit",
            side_effect=lambda fn: fn(),
        ):
            response = support_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(GlobalSupportTicket.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)
        ticket = GlobalSupportTicket.objects.first()
        msg = Message.objects.first()
        self.assertEqual(ticket.metadata.get("communication_message_id"), msg.pk)
        self.assertIn("ai_triage", ticket.metadata)
        self.assertEqual(
            ticket.metadata["ai_triage"]["suggestions"].get("category"),
            "ACCESS",
        )
        mock_invoke.assert_called()

    @override_settings(
        SUPPORT_AI_AUTO_TRIAGE_ON_CREATE=False,
        SUPPORT_TICKET_NOTIFY_EMAIL=False,
        SUPPORT_TICKET_NOTIFY_INAPP=False,
    )
    @patch("apps.portal.runtime_helpers.get_policy_for_request")
    @patch("services.ai_gateway.invoke")
    def test_post_without_auto_triage_skips_ai_metadata(
        self, mock_invoke, mock_policy
    ):
        mock_policy.return_value = {"plan_slug": "basic", "country_code": "CM"}
        rf = RequestFactory()
        path = reverse("portal:support_request")
        data = {
            "category": "FEEDBACK",
            "subject": "Nice app",
            "message": "Thanks team.",
        }
        request = _sessioned_request(rf, self.sender, self.school, path, data)
        with patch(
            "apps.portal.views_support.transaction.on_commit",
            side_effect=lambda fn: fn(),
        ):
            support_request(request)
        ticket = GlobalSupportTicket.objects.first()
        self.assertIsNotNone(ticket)
        self.assertNotIn("ai_triage", ticket.metadata)
        mock_invoke.assert_not_called()
