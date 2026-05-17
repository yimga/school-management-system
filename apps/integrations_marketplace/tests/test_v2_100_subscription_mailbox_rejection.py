"""Tests for v2.100 — calendar push-subscription renewal, mailbox fetch,
and webhook-rejection persistence.

DB-free where possible: HTTP is mocked via `unittest.mock.patch`, AuditLog
writes are stubbed.
"""

from __future__ import annotations

import time
from unittest import mock

from django.test import SimpleTestCase

from apps.integrations_marketplace import (
    mailbox_fetch as im_mailbox,
    subscription_renewal as im_renew,
    webhooks as im_webhooks,
)
from apps.integrations_marketplace.signals import mailbox_message_received


class _FakeSchool:
    def __init__(self, pk=1):
        self.pk = pk


class _FakeRow:
    def __init__(self, *, pk=1, slug="google_calendar", config=None,
                 school=None, is_active=True):
        self.pk = pk
        self.connector_slug = slug
        self.config = dict(config or {})
        self.school = school
        self.is_active = is_active
        self.saved_with: list[list[str]] = []

    def save(self, update_fields=None):
        self.saved_with.append(list(update_fields or []))


# ---------------------------------------------------------------------------
# Gap 1 — subscription renewal
# ---------------------------------------------------------------------------

class IsDueTests(SimpleTestCase):
    def test_no_provider_is_not_due(self):
        self.assertFalse(im_renew._is_due({}))
        self.assertFalse(im_renew._is_due({"provider": "google_calendar"}))

    def test_within_window_is_due(self):
        now = 1_000_000.0
        sub = {"provider": "google_calendar",
               "expires_at": now + im_renew.RENEWAL_WINDOW_SECONDS - 60}
        self.assertTrue(im_renew._is_due(sub, now=now))

    def test_outside_window_is_not_due(self):
        now = 1_000_000.0
        sub = {"provider": "google_calendar",
               "expires_at": now + im_renew.RENEWAL_WINDOW_SECONDS + 86400}
        self.assertFalse(im_renew._is_due(sub, now=now))


class RenewSingleTests(SimpleTestCase):
    def test_no_subscription_returns_no_subscription(self):
        row = _FakeRow(slug="google_calendar", config={})
        out = im_renew.renew_single(row)
        self.assertEqual(out["status"], "no_subscription")
        self.assertEqual(row.saved_with, [])

    def test_unknown_provider_returns_no_renewer(self):
        row = _FakeRow(slug="random_slug", config={
            "push_subscription": {"provider": "made_up", "expires_at": time.time()},
        })
        out = im_renew.renew_single(row)
        self.assertEqual(out["status"], "no_renewer_for_provider")

    def test_google_renewal_success_persists_new_metadata(self):
        row = _FakeRow(slug="google_calendar", config={
            "access_token": "tok",
            "push_subscription": {
                "provider": "google_calendar",
                "address": "https://app.example/integrations/webhook/google_calendar/1/",
                "channel_id": "old-channel",
                "resource_id": "old-resource",
                "expires_at": time.time() + 60,
            },
        })
        # First call: events.watch returns new channel.
        # Second call: channels/stop returns 204.
        responses = [
            (200, {"id": "new-channel", "resourceId": "new-resource"}),
            (204, {}),
        ]
        with mock.patch.object(im_renew, "_post_json", side_effect=responses):
            out = im_renew.renew_single(row)
        self.assertEqual(out["status"], "renewed")
        sub = row.config["push_subscription"]
        self.assertEqual(sub["channel_id"], "new-channel")
        self.assertEqual(sub["resource_id"], "new-resource")
        self.assertNotIn("last_renewal_error", sub)
        self.assertTrue(row.saved_with)

    def test_google_renewal_401_marks_unauthorized(self):
        row = _FakeRow(slug="google_calendar", config={
            "access_token": "tok",
            "push_subscription": {
                "provider": "google_calendar",
                "address": "https://x/",
                "expires_at": time.time(),
            },
        })
        with mock.patch.object(im_renew, "_post_json", return_value=(401, {})):
            out = im_renew.renew_single(row)
        self.assertEqual(out["status"], "unauthorized")
        self.assertEqual(row.config["push_subscription"]["last_renewal_error"], "google_401")

    def test_graph_renewal_success(self):
        row = _FakeRow(slug="outlook_calendar", config={
            "access_token": "tok",
            "push_subscription": {
                "provider": "outlook_calendar",
                "subscription_id": "sub-1",
                "expires_at": time.time(),
            },
        })
        with mock.patch.object(im_renew, "_post_json", return_value=(200, {"id": "sub-1"})):
            out = im_renew.renew_single(row)
        self.assertEqual(out["status"], "renewed")
        self.assertEqual(row.config["push_subscription"]["subscription_id"], "sub-1")

    def test_graph_renewal_missing_subscription_id_fails(self):
        row = _FakeRow(slug="outlook_calendar", config={
            "access_token": "tok",
            "push_subscription": {"provider": "outlook_calendar",
                                   "expires_at": time.time()},
        })
        out = im_renew.renew_single(row)
        self.assertEqual(out["status"], "renewal_failed")
        self.assertEqual(out["reason"], "no_subscription_id")

    def test_transport_error_keeps_row_active(self):
        row = _FakeRow(slug="google_calendar", config={
            "access_token": "tok",
            "push_subscription": {
                "provider": "google_calendar", "address": "https://x/",
                "expires_at": time.time(),
            },
        })
        with mock.patch.object(im_renew, "_post_json", return_value=(0, {})):
            out = im_renew.renew_single(row)
        self.assertEqual(out["status"], "transport_error")
        self.assertTrue(row.is_active)


# ---------------------------------------------------------------------------
# Gap 2 — mailbox fetch
# ---------------------------------------------------------------------------

class MailboxFetchTests(SimpleTestCase):
    def setUp(self):
        self.received: list[dict] = []

        def receiver(sender, **kw):
            self.received.append({k: v for k, v in kw.items() if k != "signal"})

        # Hold a strong ref so Django's weak-ref dispatcher doesn't GC it.
        self._receiver = receiver
        mailbox_message_received.connect(
            receiver, dispatch_uid="im_test_mailbox", weak=False
        )
        self.addCleanup(
            lambda: mailbox_message_received.disconnect(dispatch_uid="im_test_mailbox")
        )

    def test_no_fetcher_for_unknown_slug(self):
        row = _FakeRow(slug="random_slug")
        out = im_mailbox.fetch_single(row)
        self.assertEqual(out["status"], "no_fetcher_for_slug")

    def test_unauthorized_when_no_access_token(self):
        row = _FakeRow(slug="gmail", config={})
        out = im_mailbox.fetch_single(row)
        self.assertEqual(out["status"], "unauthorized")

    def test_gmail_fetch_dispatches_signal_per_new_message(self):
        row = _FakeRow(slug="gmail", config={"access_token": "tok"})
        # 1st call: list returns 2 message ids.
        # 2nd+3rd: each message detail.
        responses = [
            (200, {"messages": [{"id": "m1"}, {"id": "m2"}]}),
            (200, {"id": "m1", "snippet": "hello"}),
            (200, {"id": "m2", "snippet": "world"}),
        ]
        with mock.patch.object(im_mailbox, "_http_get_json", side_effect=responses):
            out = im_mailbox.fetch_single(row)
        self.assertEqual(out["status"], "fetched")
        self.assertEqual(out["delivered"], 2)
        self.assertEqual(len(self.received), 2)
        self.assertEqual(self.received[0]["provider"], "gmail")
        # Cursor advanced to newest seen.
        self.assertEqual(row.config["mailbox_state"]["last_message_id"], "m1")

    def test_gmail_cursor_stops_at_last_seen(self):
        row = _FakeRow(slug="gmail", config={
            "access_token": "tok",
            "mailbox_state": {"last_message_id": "m_seen"},
        })
        # List returns 3 msgs, second one is the cursor — loop stops there.
        responses = [
            (200, {"messages": [{"id": "m_new1"}, {"id": "m_seen"}, {"id": "m_new2"}]}),
            (200, {"id": "m_new1"}),
        ]
        with mock.patch.object(im_mailbox, "_http_get_json", side_effect=responses):
            out = im_mailbox.fetch_single(row)
        self.assertEqual(out["delivered"], 1)
        self.assertEqual(len(self.received), 1)

    def test_outlook_fetch_dispatches_signal_per_message(self):
        row = _FakeRow(slug="outlook_mail", config={"access_token": "tok"})
        responses = [
            (200, {"value": [
                {"id": "g1", "subject": "Hi"},
                {"id": "g2", "subject": "There"},
            ]}),
        ]
        with mock.patch.object(im_mailbox, "_http_get_json", side_effect=responses):
            out = im_mailbox.fetch_single(row)
        self.assertEqual(out["delivered"], 2)
        self.assertEqual(len(self.received), 2)
        self.assertEqual(self.received[0]["provider"], "outlook_mail")

    def test_401_marks_unauthorized_and_persists_error(self):
        row = _FakeRow(slug="gmail", config={"access_token": "tok"})
        with mock.patch.object(im_mailbox, "_http_get_json", return_value=(401, {})):
            out = im_mailbox.fetch_single(row)
        self.assertEqual(out["status"], "unauthorized")
        self.assertEqual(row.config["mailbox_state"]["last_fetch_error"], "gmail_401")

    def test_robust_signal_dispatch_swallows_subscriber_crash(self):
        # A second subscriber raises — first must still see the message.
        def boom(sender, **kw):
            raise RuntimeError("subscriber bug")
        self._boom = boom  # strong ref to avoid GC
        mailbox_message_received.connect(boom, dispatch_uid="im_test_boom", weak=False)
        try:
            row = _FakeRow(slug="gmail", config={"access_token": "tok"})
            responses = [
                (200, {"messages": [{"id": "m1"}]}),
                (200, {"id": "m1"}),
            ]
            with mock.patch.object(im_mailbox, "_http_get_json", side_effect=responses):
                out = im_mailbox.fetch_single(row)
            self.assertEqual(out["status"], "fetched")
            self.assertEqual(len(self.received), 1)
        finally:
            mailbox_message_received.disconnect(dispatch_uid="im_test_boom")


# ---------------------------------------------------------------------------
# Gap 3 — webhook rejection persistence
# ---------------------------------------------------------------------------

class WebhookRejectionPersistenceTests(SimpleTestCase):
    def test_persist_rejection_writes_audit_row(self):
        row = _FakeRow(slug="slack", school=_FakeSchool(pk=5))
        with mock.patch(
            "apps.compliance.models_audit.AuditLog.objects.create"
        ) as create:
            im_webhooks._persist_rejection(
                connector="slack", row=row, reason="signature_mismatch",
                client_ip="3.4.5.6",
            )
        create.assert_called_once()
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["reason"], "webhook_rejected:signature_mismatch")
        self.assertEqual(kwargs["app_label"], "integrations_marketplace")
        self.assertEqual(kwargs["new_values"]["school_id"], 5)
        self.assertEqual(kwargs["new_values"]["client_ip"], "3.4.5.6")
        self.assertEqual(kwargs["new_values"]["connector"], "slack")

    def test_persist_rejection_swallows_db_error(self):
        row = _FakeRow(slug="slack")
        with mock.patch(
            "apps.compliance.models_audit.AuditLog.objects.create",
            side_effect=RuntimeError("DB down"),
        ):
            # Must NOT raise — rejection logging is best-effort.
            im_webhooks._persist_rejection(
                connector="slack", row=row, reason="x", client_ip="1.1.1.1"
            )

    def test_persist_rejection_handles_missing_audit_log_module(self):
        # Simulate compliance app uninstalled — function must noop silently.
        import sys
        original = sys.modules.get("apps.compliance.models_audit")
        sys.modules.pop("apps.compliance.models_audit", None)
        try:
            with mock.patch.dict(
                sys.modules,
                {"apps.compliance.models_audit": None},
            ):
                # When sys.modules entry is None Python raises ImportError on import.
                # The function should swallow it cleanly.
                im_webhooks._persist_rejection(
                    connector="slack", row=_FakeRow(), reason="x", client_ip="0.0.0.0"
                )
        finally:
            if original is not None:
                sys.modules["apps.compliance.models_audit"] = original
