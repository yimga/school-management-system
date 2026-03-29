"""SLA breach helpers against persisted GlobalSupportTicket rows (time-shifted)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import School
from apps.siteconfig.models_feature_controls import GlobalSupportTicket
from apps.siteconfig.support_sla import (
    get_sla_resolution_hours,
    get_sla_response_hours,
    ticket_resolution_breach,
    ticket_response_breach,
)


class SupportSlaTicketHelpersTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="SLA School",
            slug="sla-school",
            subdomain="sla-school",
            is_active=True,
        )
        self.user = User.objects.create_user(username="sla-user", password="pass")

    def test_get_sla_hours_fallback_normal(self):
        self.assertEqual(get_sla_response_hours("NORMAL"), 24)
        self.assertGreater(get_sla_resolution_hours("NORMAL"), 0)

    def test_response_no_breach_when_first_response_exists(self):
        t = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.user,
            subject="S",
            body="B",
            priority=GlobalSupportTicket.Priority.NORMAL,
        )
        now = timezone.now()
        GlobalSupportTicket.objects.filter(pk=t.pk).update(
            created_at=now - timedelta(hours=200),
            first_response_at=now - timedelta(hours=100),
        )
        t.refresh_from_db()
        self.assertFalse(ticket_response_breach(t))

    def test_response_breach_when_past_deadline_no_first_response(self):
        t = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.user,
            subject="S",
            body="B",
            priority=GlobalSupportTicket.Priority.NORMAL,
        )
        GlobalSupportTicket.objects.filter(pk=t.pk).update(
            created_at=timezone.now() - timedelta(hours=100),
            first_response_at=None,
        )
        t.refresh_from_db()
        self.assertTrue(ticket_response_breach(t))

    def test_resolution_no_breach_when_closed(self):
        t = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.user,
            subject="S",
            body="B",
            status=GlobalSupportTicket.Status.CLOSED,
        )
        GlobalSupportTicket.objects.filter(pk=t.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        t.refresh_from_db()
        self.assertFalse(ticket_resolution_breach(t))

    def test_resolution_breach_when_open_and_stale(self):
        t = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.user,
            subject="S",
            body="B",
            status=GlobalSupportTicket.Status.OPEN,
            priority=GlobalSupportTicket.Priority.NORMAL,
        )
        GlobalSupportTicket.objects.filter(pk=t.pk).update(
            created_at=timezone.now() - timedelta(days=14),
        )
        t.refresh_from_db()
        self.assertTrue(ticket_resolution_breach(t))
