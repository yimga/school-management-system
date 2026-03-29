"""HTTP tests for super support dashboard and queue fragment (manager host)."""

import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorSupportDashboardLink
from apps.schools.models import School
from apps.siteconfig.models_feature_controls import (
    GlobalSupportTicket,
    GlobalSupportTicketReply,
)


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class SuperSupportQueueHttpTests(TestCase):
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
            username="queue-ops",
            email="queue@example.com",
            password="pass1234",
        )
        self.school = School.objects.create(
            name="Queue School",
            slug="queue-school",
            subdomain="queue-school",
            is_active=True,
        )
        GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.superuser,
            subject="Queue item",
            body="Body",
            status=GlobalSupportTicket.Status.OPEN,
            priority=GlobalSupportTicket.Priority.HIGH,
        )

    def tearDown(self):
        self.env.stop()

    def test_support_dashboard_get(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Queue item")

    def test_support_dashboard_phase_h_skip_link_targets_main(self):
        """Batch 25 #286 — Phase H skip target for support mission control (manager host)."""
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#support-dashboard-main"', body)
        self.assertIn('id="support-dashboard-main"', body)

    def test_support_dashboard_renders_operator_support_dashboard_curated_links(self):
        PlatformOperatorSupportDashboardLink.objects.create(
            slug="batch-27-pulse",
            label="Open pulse map",
            href="/super/pulse/",
            sort_order=0,
        )
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open pulse map", body)
        self.assertIn('href="/super/pulse/"', body)

    def test_support_queue_fragment_get(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/queue/", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Queue item")

    def test_support_tickets_export_csv(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/export.csv",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.get("Content-Type", ""))
        body = response.content.decode()
        self.assertIn("ticket_id", body)
        self.assertIn("Queue item", body)

    def test_support_dashboard_status_filter(self):
        GlobalSupportTicket.objects.filter(subject="Queue item").update(
            status=GlobalSupportTicket.Status.RESOLVED
        )
        GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.superuser,
            subject="Still open",
            body="B",
            status=GlobalSupportTicket.Status.OPEN,
        )
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/?status=OPEN",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Still open")
        self.assertNotContains(response, "Queue item")

    def test_support_tickets_export_csv_respects_status_filter(self):
        GlobalSupportTicket.objects.filter(subject="Queue item").update(
            status=GlobalSupportTicket.Status.RESOLVED
        )
        GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.superuser,
            subject="Export open only",
            body="x",
            status=GlobalSupportTicket.Status.OPEN,
        )
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/export.csv",
            {"status": "OPEN"},
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Export open only", body)
        self.assertNotIn("Queue item", body)

    def test_support_tickets_export_csv_respects_priority_filter(self):
        GlobalSupportTicket.objects.filter(subject="Queue item").update(
            priority=GlobalSupportTicket.Priority.NORMAL
        )
        GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.superuser,
            subject="Urgent export row",
            body="x",
            status=GlobalSupportTicket.Status.OPEN,
            priority=GlobalSupportTicket.Priority.URGENT,
        )
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/export.csv",
            {"priority": "URGENT"},
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Urgent export row", body)
        self.assertNotIn("Queue item", body)

    def test_super_post_reply_submitter_visible_sets_first_response(self):
        submitter = User.objects.create_user(
            username="ticket-owner",
            password="pass",
            email="owner@example.com",
        )
        ticket = GlobalSupportTicket.objects.create(
            school=self.school,
            user=submitter,
            subject="Needs help",
            body="Hi",
            status=GlobalSupportTicket.Status.OPEN,
        )
        self.assertIsNone(ticket.first_response_at)
        self.client.force_login(self.superuser)
        url = reverse("super:support_ticket_detail", kwargs={"ticket_id": ticket.pk})
        response = self.client.post(
            url,
            {
                "action": "reply",
                "reply_body": "Fixed in release 12.",
                "reply_visibility": "SUBMITTER_VISIBLE",
            },
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(GlobalSupportTicketReply.objects.filter(ticket=ticket).count(), 1)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.first_response_at)

    def test_support_csat_dashboard_get(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/csat/",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CSAT")

    def test_support_csat_dashboard_phase_h_skip_link_targets_main(self):
        """Batch 26 #301 — Phase H skip target for global support CSAT (manager host)."""
        self.client.force_login(self.superuser)
        response = self.client.get(
            "/super/support/csat/",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#support-csat-dashboard-main"', body)
        self.assertIn('id="support-csat-dashboard-main"', body)

    def test_support_assign_htmx_fragment_respects_status_filter(self):
        """After assign, HTMX fragment must filter before slice (same as queue fragment)."""
        open_t = GlobalSupportTicket.objects.get(subject="Queue item")
        GlobalSupportTicket.objects.filter(pk=open_t.pk).update(
            status=GlobalSupportTicket.Status.RESOLVED
        )
        GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.superuser,
            subject="Still open for assign test",
            body="b",
            status=GlobalSupportTicket.Status.OPEN,
        )
        self.client.force_login(self.superuser)
        still_open = GlobalSupportTicket.objects.get(subject="Still open for assign test")
        response = self.client.post(
            f"{reverse('super:support_assign_ticket')}?status=OPEN",
            {"ticket_id": str(still_open.pk), "action": "assign_me"},
            HTTP_HOST="manager.runmycampus.com",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Still open for assign test")
        self.assertNotContains(response, "Queue item")
