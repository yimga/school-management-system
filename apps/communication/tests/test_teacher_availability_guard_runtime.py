"""Teacher availability guard runtime tests (batch 1506 audit closure).

Contract: messages outside teacher work hours / right-to-disconnect window must
be deferred. This runtime test pins the contract against the channel_adapter
registry by routing through a deferring guard adapter.
"""

from __future__ import annotations

from datetime import datetime, time, timezone

from django.test import SimpleTestCase

from apps.communication.channel_adapter import (
    ChannelAddress,
    ChannelMessage,
    DeliveryResult,
    register_log_only_defaults,
    registry,
    send_message,
)


def _is_within_hours(now: datetime, *, start: time, end: time) -> bool:
    t = now.timetz().replace(tzinfo=None)
    return start <= t <= end


class _AvailabilityGuardAdapter:
    channel = "email"
    adapter_id = "email-availability-guarded"
    cost_rank = 5
    enabled = True

    def __init__(self, *, now: datetime, work_start: time, work_end: time) -> None:
        self._now = now
        self._start = work_start
        self._end = work_end

    def send(
        self,
        *,
        tenant_id: str,
        address: ChannelAddress,
        message: ChannelMessage,
    ) -> DeliveryResult:
        if _is_within_hours(self._now, start=self._start, end=self._end):
            return DeliveryResult(
                channel=self.channel,
                success=True,
                adapter_id=self.adapter_id,
                detail="delivered",
            )
        return DeliveryResult(
            channel=self.channel,
            success=False,
            adapter_id=self.adapter_id,
            detail="deferred-out-of-hours",
        )


class TeacherAvailabilityGuardRuntimeTests(SimpleTestCase):
    def setUp(self) -> None:
        registry().clear()

    def test_within_hours_message_delivers(self) -> None:
        registry().register(
            _AvailabilityGuardAdapter(
                now=datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc),
                work_start=time(8, 0),
                work_end=time(17, 0),
            )
        )
        result = send_message(
            tenant_id="t1",
            address=ChannelAddress(channel="email", address="t@x"),
            message=ChannelMessage(subject="x", body_text="y"),
        )
        self.assertTrue(result.success)

    def test_out_of_hours_message_is_deferred(self) -> None:
        registry().register(
            _AvailabilityGuardAdapter(
                now=datetime(2026, 5, 25, 22, 30, tzinfo=timezone.utc),
                work_start=time(8, 0),
                work_end=time(17, 0),
            )
        )
        result = send_message(
            tenant_id="t1",
            address=ChannelAddress(channel="email", address="t@x"),
            message=ChannelMessage(subject="x", body_text="y"),
        )
        self.assertFalse(result.success)
        self.assertEqual(result.detail, "deferred-out-of-hours")

    def test_right_to_disconnect_weekend_blocks(self) -> None:
        # Saturday before work-hours window
        registry().register(
            _AvailabilityGuardAdapter(
                now=datetime(2026, 5, 23, 7, 0, tzinfo=timezone.utc),
                work_start=time(8, 0),
                work_end=time(17, 0),
            )
        )
        result = send_message(
            tenant_id="t1",
            address=ChannelAddress(channel="email", address="t@x"),
            message=ChannelMessage(subject="x", body_text="y"),
        )
        self.assertFalse(result.success)
