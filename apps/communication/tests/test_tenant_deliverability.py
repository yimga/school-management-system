"""Tests for ``apps.communication.tenant_deliverability``."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.communication.tenant_deliverability import (
    DeliverabilityEvent,
    aggregate,
)


def _ev(school_id: int, status: str) -> DeliverabilityEvent:
    return DeliverabilityEvent(school_id=school_id, status=status, occurred_at="2026-05-17T00:00:00Z")


class AggregateTests(SimpleTestCase):
    def test_empty_events_empty_report(self):
        self.assertEqual(aggregate([]), [])

    def test_healthy_tenant(self):
        events = [_ev(1, "delivered")] * 999 + [_ev(1, "bounced")] * 1
        # 1/1000 = 0.001 bounce -> healthy.
        reports = aggregate(events)
        self.assertEqual(len(reports), 1)
        r = reports[0]
        self.assertEqual(r.school_id, 1)
        self.assertEqual(r.sent, 1000)
        self.assertEqual(r.bounced, 1)
        self.assertEqual(r.health, "healthy")

    def test_warning_band(self):
        # 30 bounces / 1000 -> 3% bounce -> "warning"
        events = [_ev(2, "delivered")] * 970 + [_ev(2, "bounced")] * 30
        reports = aggregate(events)
        self.assertEqual(reports[0].health, "warning")

    def test_critical_band(self):
        # 80 bounces / 1000 -> 8% bounce -> critical
        events = [_ev(3, "delivered")] * 920 + [_ev(3, "bounced")] * 80
        reports = aggregate(events)
        self.assertEqual(reports[0].health, "critical")

    def test_complaint_pushes_to_critical(self):
        # Low bounce, but 1% complaint -> critical.
        events = (
            [_ev(4, "delivered")] * 989
            + [_ev(4, "bounced")] * 1
            + [_ev(4, "complained")] * 10
        )
        reports = aggregate(events)
        self.assertEqual(reports[0].health, "critical")

    def test_per_tenant_isolation(self):
        events = (
            [_ev(10, "delivered")] * 990
            + [_ev(10, "bounced")] * 10
            + [_ev(20, "delivered")] * 100
            + [_ev(20, "bounced")] * 100
        )
        reports = aggregate(events)
        self.assertEqual(len(reports), 2)
        by_id = {r.school_id: r for r in reports}
        self.assertEqual(by_id[10].health, "healthy")
        self.assertEqual(by_id[20].health, "critical")

    def test_unsubscribe_rate_does_not_affect_health(self):
        events = (
            [_ev(5, "delivered")] * 990
            + [_ev(5, "bounced")] * 5
            + [_ev(5, "unsubscribed")] * 50
        )
        reports = aggregate(events)
        self.assertEqual(reports[0].health, "healthy")
        self.assertGreater(reports[0].unsubscribe_rate, 0)

    def test_unknown_status_ignored(self):
        events = [_ev(6, "delivered")] * 100 + [_ev(6, "weird-status")] * 50
        reports = aggregate(events)
        self.assertEqual(reports[0].delivered, 100)
        # bounce / complaint / unsubscribe / suppressed all 0.
        self.assertEqual(reports[0].bounced, 0)
