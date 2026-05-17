"""Tests for v2.89 follow-up #2:
  - `webhook_received` Django signal fires on every audited handler call
  - per-receiver crashes don't break the ack (Django's send_robust)
  - the signal carries the row, connector, event_type, payload

DB-free: handlers are exercised via `_audit` with mocked AuditLog persistence;
signal receivers run in-process.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.integrations_marketplace import webhook_handlers as handlers
from apps.integrations_marketplace.signals import webhook_received


class _FakeRow:
    def __init__(self, slug="slack", school=None, campus=None, pk=1):
        self.connector_slug = slug
        self.config = {}
        self.school = school
        self.campus = campus
        self.pk = pk


class WebhookSignalTests(SimpleTestCase):
    def setUp(self):
        # Don't actually hit the DB for audit.
        patcher = mock.patch(
            "apps.compliance.models_audit.AuditLog.objects.create"
        )
        self.addCleanup(patcher.stop)
        patcher.start()

        # Track signal receiver invocations.
        self.received: list[dict] = []

        def receiver(sender, **kw):
            self.received.append({k: v for k, v in kw.items() if k != "signal"})

        webhook_received.connect(receiver, dispatch_uid="im_test_receiver")
        self.addCleanup(
            lambda: webhook_received.disconnect(dispatch_uid="im_test_receiver")
        )
        self.receiver = receiver

    def test_audit_fires_signal_with_full_kwargs(self):
        row = _FakeRow(slug="slack", pk=42)
        handlers._audit("slack", row, "events_api.message", {"event": "x"})
        self.assertEqual(len(self.received), 1)
        kw = self.received[0]
        self.assertIs(kw["row"], row)
        self.assertEqual(kw["connector"], "slack")
        self.assertEqual(kw["event_type"], "events_api.message")
        self.assertEqual(kw["payload"], {"event": "x"})

    def test_audit_normalizes_non_dict_payload_to_empty(self):
        row = _FakeRow(slug="zoom")
        handlers._audit("zoom", row, "recording.completed", "not-a-dict")
        self.assertEqual(self.received[-1]["payload"], {})

    def test_signal_receiver_crash_does_not_break_ack(self):
        # Subscribe a second receiver that always raises; send_robust must
        # catch it and the first receiver must still fire.
        def boom(sender, **kw):
            raise RuntimeError("subscriber bug")

        webhook_received.connect(boom, dispatch_uid="im_test_boom")
        try:
            row = _FakeRow(slug="stripe")
            # Must NOT raise even though boom() does.
            handlers._audit("stripe", row, "charge.succeeded", {"id": "ch_1"})
            self.assertEqual(len(self.received), 1)
        finally:
            webhook_received.disconnect(dispatch_uid="im_test_boom")

    def test_slack_handler_via_audit_fires_signal_once(self):
        row = _FakeRow(slug="slack")
        # Use an event_callback so handle_slack falls into the audit branch.
        resp = handlers.handle_slack(
            row, {"type": "event_callback", "event": {"type": "message"}}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0]["connector"], "slack")
        self.assertEqual(self.received[0]["event_type"], "events_api.message")


class IntegrationsEventsViewTests(SimpleTestCase):
    """Smoke-test the data-shape contract of integrations_events without
    standing up a full tenant. We exercise the queryset-iteration loop by
    mocking AuditLog.objects to return a fabricated rowset and asserting
    only this tenant's school_id makes it through.
    """

    def _fake_audit_row(self, *, school_id, connector, event_type, pk=1):
        m = mock.Mock()
        m.timestamp = "2026-05-16T11:00:00"
        m.new_values = {
            "school_id": school_id,
            "connector": connector,
            "event_type": event_type,
            "campus_id": None,
            "payload_keys": ["a", "b"],
        }
        m.object_id = "99"
        m.pk = pk
        return m

    def test_view_filters_by_tenant_and_connector(self):
        # We test the inner loop logic directly by importing the view and
        # exercising the iteration with a hand-rolled iterable.
        from apps.integrations_marketplace import views as im_views

        rows = [
            self._fake_audit_row(school_id=1, connector="slack", event_type="x"),
            self._fake_audit_row(school_id=2, connector="slack", event_type="x"),  # wrong tenant
            self._fake_audit_row(school_id=1, connector="zoom", event_type="y"),
            self._fake_audit_row(school_id=1, connector="slack", event_type="z"),
        ]

        # Build a fake request with school + connector filter.
        request = mock.Mock()
        request.school = mock.Mock(pk=1)
        request.user = mock.Mock(is_authenticated=True, is_staff=True, is_superuser=False, role="admin")
        request.GET = {"connector": "slack"}

        # Stub render so we can capture the context.
        captured: dict = {}

        def fake_render(req, tmpl, ctx, **kw):
            captured["template"] = tmpl
            captured["ctx"] = ctx
            from django.http import HttpResponse
            return HttpResponse("ok")

        # Stub AuditLog.objects.filter().order_by().iterator() chain.
        qs = mock.Mock()
        qs.iterator.return_value = iter(rows)
        order = mock.Mock(return_value=qs)
        filt = mock.Mock(return_value=mock.Mock(order_by=order))
        with mock.patch("apps.compliance.models_audit.AuditLog.objects.filter", filt), \
             mock.patch.object(im_views, "render", side_effect=fake_render):
            im_views.integrations_events(request)

        events = captured["ctx"]["events"]
        # 2 events for school 1 + connector slack; school 2 row filtered out;
        # zoom row filtered out by connector filter.
        self.assertEqual(len(events), 2)
        for e in events:
            self.assertEqual(e["connector"], "slack")
