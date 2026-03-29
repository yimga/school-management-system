import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.communication.models import Message
from apps.platform_runtime.models import PlatformEventLog
from apps.schools.models import School
from apps.siteconfig.models_feature_controls import GlobalSupportTicket


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class SuperSupportTicketDetailTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.superuser = User.objects.create_superuser(
            username="support-ops",
            email="support-ops@example.com",
            password="pass1234",
        )
        self.school = School.objects.create(
            name="Ticket Detail School",
            slug="ticket-detail-school",
            subdomain="ticket-detail-school",
            is_active=True,
        )
        self.ticket = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.superuser,
            subject="Printer on fire",
            body="Please advise.",
            status=GlobalSupportTicket.Status.OPEN,
        )
        PlatformEventLog.objects.filter(
            event_type__startswith="support_desk_"
        ).delete()

    def tearDown(self):
        self.env.stop()

    def test_detail_get_does_not_spam_view_audit(self):
        self.client.force_login(self.superuser)
        url = f"/super/support/ticket/{self.ticket.pk}/"
        response = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Printer on fire")
        self.assertFalse(
            PlatformEventLog.objects.filter(
                event_type="support_desk_ticket_viewed"
            ).exists()
        )

    def test_detail_post_updates_and_audits(self):
        self.client.force_login(self.superuser)
        url = f"/super/support/ticket/{self.ticket.pk}/"
        response = self.client.post(
            url,
            {"status": "IN_PROGRESS", "internal_notes": "Called tenant."},
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, GlobalSupportTicket.Status.IN_PROGRESS)
        self.assertEqual(self.ticket.internal_notes, "Called tenant.")
        log = PlatformEventLog.objects.filter(
            event_type="support_desk_ticket_updated"
        ).first()
        self.assertIsNotNone(log)
        payload = log.payload or {}
        self.assertIn("internal_notes", payload.get("changed_fields") or [])

    def test_assign_posts_emit_assignment_event(self):
        self.client.force_login(self.superuser)
        PlatformEventLog.objects.filter(
            event_type="support_desk_ticket_assignment_changed"
        ).delete()
        self.client.post(
            "/super/support/assign/",
            {"ticket_id": str(self.ticket.pk), "action": "assign_me"},
            HTTP_HOST="manager.runmycampus.com",
        )
        log = PlatformEventLog.objects.filter(
            event_type="support_desk_ticket_assignment_changed"
        ).first()
        self.assertIsNotNone(log)
        payload = log.payload or {}
        self.assertEqual(payload.get("action"), "assign_me")
        self.assertEqual(payload.get("assignee_id"), self.superuser.pk)

    def test_detail_shows_ai_triage_and_message_admin_link(self):
        msg = Message.objects.create(
            sender=self.superuser,
            recipient=self.superuser,
            subject="Support relay",
            body="Relay body",
            school=self.school,
        )
        self.ticket.metadata = {
            "communication_message_id": msg.pk,
            "ai_triage": {
                "at": "2026-03-27T12:00:00",
                "suggestions": {
                    "category": "BILLING",
                    "priority": "NORMAL",
                    "suggested_reply": "Please check your invoice tab.",
                },
                "suggested_reply_preview": "Please check your invoice tab.",
                "gateway": {"gateway": True},
            },
        }
        self.ticket.save(update_fields=["metadata"])
        self.client.force_login(self.superuser)
        url = f"/super/support/ticket/{self.ticket.pk}/"
        response = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI triage")
        self.assertContains(response, "BILLING")
        self.assertContains(response, "invoice tab")
        self.assertContains(response, "/admin/communication/message/")
