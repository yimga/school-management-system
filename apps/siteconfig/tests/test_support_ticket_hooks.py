"""Unit tests for apps.siteconfig.support_ticket_hooks (notify, webhooks, outbox)."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.communication.models import Message
from apps.schools.models import School
from apps.siteconfig.models_feature_controls import (
    GlobalSupportTicket,
    GlobalSupportTicketWebhookEndpoint,
)
from apps.siteconfig.support_ticket_hooks import (
    run_support_ticket_created_hooks,
    run_support_ticket_csat_hooks,
    run_support_ticket_reply_hooks,
)


def _immediate_on_commit(fn):
    fn()


class SupportTicketCreatedHooksTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Hook School",
            slug="hook-school",
            subdomain="hook-school",
            is_active=True,
        )
        self.submitter = User.objects.create_user(
            username="hook-sub",
            password="pass",
            role=User.Role.ADMIN,
            email="sub@example.com",
        )
        User.objects.create_user(
            username="hook-it1",
            password="pass",
            role=User.Role.IT_ADMIN,
            email="it1@example.com",
        )
        User.objects.create_user(
            username="hook-it2",
            password="pass",
            role=User.Role.IT_ADMIN,
            email="it2@example.com",
        )
        self.ticket = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.submitter,
            subject="Login issue",
            body="Cannot sign in.",
            status=GlobalSupportTicket.Status.OPEN,
        )

    @patch("apps.siteconfig.support_ticket_hooks.transaction.on_commit", _immediate_on_commit)
    @patch("apps.siteconfig.tasks.deliver_support_ticket_http_webhook.apply_async")
    @patch("apps.events.webhooks.enqueue_webhook_event")
    @patch("apps.communication.notification_service.send_email")
    @patch("apps.platform_runtime.events.emit_platform_event")
    @override_settings(
        SUPPORT_TICKET_WEBHOOK_URL="https://legacy.example/webhook",
        SUPPORT_TICKET_WEBHOOK_SECRET="sec",
    )
    def test_created_hooks_send_email_enqueue_and_schedule_legacy_webhook(
        self,
        _emit,
        mock_email,
        mock_enqueue,
        mock_apply_async,
    ):
        run_support_ticket_created_hooks(str(self.ticket.pk), primary_recipient_id=None)
        mock_email.assert_called()
        args, kwargs = mock_email.call_args
        self.assertGreaterEqual(len(args[0]), 1)
        mock_enqueue.assert_called_once()
        mock_apply_async.assert_called_once()
        wh_kwargs = mock_apply_async.call_args.kwargs.get("kwargs") or {}
        self.assertEqual(wh_kwargs.get("url"), "https://legacy.example/webhook")
        self.assertEqual(
            wh_kwargs.get("payload", {}).get("event"),
            "support.global_ticket.created",
        )

    @patch("apps.siteconfig.support_ticket_hooks.transaction.on_commit", _immediate_on_commit)
    @patch("apps.siteconfig.tasks.deliver_support_ticket_http_webhook.apply_async")
    @patch("apps.events.webhooks.enqueue_webhook_event")
    @patch("apps.communication.notification_service.send_email")
    @patch("apps.platform_runtime.events.emit_platform_event")
    def test_created_hooks_schedules_db_endpoints_plus_legacy(
        self,
        _emit,
        _email,
        _enqueue,
        mock_apply_async,
    ):
        GlobalSupportTicketWebhookEndpoint.objects.create(
            name="A",
            url="https://db-a.example/hook",
            secret="a",
            is_active=True,
        )
        with self.settings(
            SUPPORT_TICKET_WEBHOOK_URL="https://legacy.example/webhook",
            SUPPORT_TICKET_WEBHOOK_SECRET="leg",
        ):
            run_support_ticket_created_hooks(str(self.ticket.pk))
        self.assertEqual(mock_apply_async.call_count, 2)
        urls = {
            (mock_apply_async.call_args_list[i].kwargs["kwargs"]["url"])
            for i in range(mock_apply_async.call_count)
        }
        self.assertSetEqual(
            urls,
            {"https://db-a.example/hook", "https://legacy.example/webhook"},
        )

    @patch("apps.platform_runtime.events.emit_platform_event")
    @override_settings(
        SUPPORT_TICKET_NOTIFY_INAPP=True,
        SUPPORT_TICKET_INAPP_FANOUT_OPERATORS=True,
        SUPPORT_TICKET_NOTIFY_EMAIL=False,
    )
    def test_inapp_fanout_creates_messages(self, _emit):
        Message.objects.all().delete()
        run_support_ticket_created_hooks(
            str(self.ticket.pk), primary_recipient_id=self.submitter.pk
        )
        self.assertGreaterEqual(Message.objects.count(), 1)


class SupportTicketCsatHooksTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="C School",
            slug="c-school",
            subdomain="c-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="c-user",
            password="pass",
            role=User.Role.ADMIN,
            email="c@example.com",
        )
        self.ticket = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.user,
            subject="Done",
            body="x",
            status=GlobalSupportTicket.Status.RESOLVED,
            csat_score=5,
            csat_comment="Great",
        )

    @patch("apps.siteconfig.support_ticket_hooks.transaction.on_commit", _immediate_on_commit)
    @patch("apps.siteconfig.tasks.deliver_support_ticket_http_webhook.apply_async")
    @patch("apps.platform_runtime.events.emit_platform_event")
    def test_csat_hooks_schedule_http_webhook(
        self,
        _emit,
        mock_apply_async,
    ):
        with self.settings(SUPPORT_TICKET_WEBHOOK_URL="https://legacy.example/hook"):
            run_support_ticket_csat_hooks(str(self.ticket.pk), actor_id=self.user.pk)
        mock_apply_async.assert_called_once()
        payload = mock_apply_async.call_args.kwargs["kwargs"]["payload"]
        self.assertEqual(payload.get("event"), "support.global_ticket.csat_submitted")
        self.assertEqual(payload.get("score"), 5)


class SupportTicketReplyHooksTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="R School",
            slug="r-school",
            subdomain="r-school",
            is_active=True,
        )
        self.submitter = User.objects.create_user(
            username="r-sub",
            password="pass",
            role=User.Role.ADMIN,
            email="tenant@example.com",
        )
        self.operator = User.objects.create_superuser(
            username="r-ops",
            email="ops@example.com",
            password="pass",
        )
        self.ticket = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.submitter,
            subject="Q",
            body="B",
        )

    @patch("apps.siteconfig.support_ticket_hooks.transaction.on_commit", _immediate_on_commit)
    @patch("apps.siteconfig.tasks.deliver_support_ticket_http_webhook.apply_async")
    @patch("apps.platform_runtime.events.emit_platform_event")
    @patch("apps.communication.notification_service.send_email")
    @override_settings(SUPPORT_TICKET_NOTIFY_SUBMITTER_ON_VISIBLE_REPLY=True)
    def test_reply_visible_emails_submitter_when_actor_is_operator(
        self,
        mock_email,
        _emit,
        _apply_async,
    ):
        run_support_ticket_reply_hooks(
            str(self.ticket.pk),
            actor_id=self.operator.pk,
            visibility="SUBMITTER_VISIBLE",
            reply_body="We shipped a fix.",
        )
        mock_email.assert_called()
        recipients = mock_email.call_args[0][0]
        self.assertIn("tenant@example.com", recipients)
