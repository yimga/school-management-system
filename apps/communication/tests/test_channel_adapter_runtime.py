"""Runtime tests for apps.communication.channel_adapter (batch 1493)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.communication.channel_adapter import (
    ChannelAdapterRegistry,
    ChannelAddress,
    ChannelMessage,
    ChannelUnavailableError,
    LoopbackTestAdapter,
    _LogOnlyAdapter,
    register_log_only_defaults,
    registry,
    send_message,
)


class ChannelAdapterRuntimeTests(SimpleTestCase):
    def setUp(self) -> None:
        registry().clear()

    def test_registry_selects_lowest_cost_when_reliability_equal(self) -> None:
        reg = ChannelAdapterRegistry()
        reg.register(_LogOnlyAdapter(channel="email", adapter_id="cheap", cost_rank=1))
        reg.register(_LogOnlyAdapter(channel="email", adapter_id="dear", cost_rank=10))
        entry = reg.select(preferred_channels=["email"])
        self.assertEqual(entry.adapter.adapter_id, "cheap")

    def test_registry_rejects_when_channel_missing(self) -> None:
        reg = ChannelAdapterRegistry()
        with self.assertRaises(ChannelUnavailableError):
            reg.select(preferred_channels=["sms"])

    def test_send_message_routes_through_registered_adapter(self) -> None:
        # Uses the explicit loopback test double: a *test* fixture may report a
        # successful send, a deployed adapter may not. _LogOnlyAdapter sends
        # nothing and therefore now reports success=False (item 0.3).
        registry().register(LoopbackTestAdapter(channel="email", adapter_id="loopback:email"))
        result = send_message(
            tenant_id="tenant-uuid-1",
            address=ChannelAddress(channel="email", address="parent@example"),
            message=ChannelMessage(subject="Note", body_text="Hello"),
        )
        self.assertTrue(result.success)
        self.assertEqual(result.adapter_id, "loopback:email")

    def test_log_only_adapter_never_reports_delivery(self) -> None:
        register_log_only_defaults()
        result = send_message(
            tenant_id="tenant-uuid-1",
            address=ChannelAddress(channel="email", address="parent@example"),
            message=ChannelMessage(subject="Note", body_text="Hello"),
        )
        self.assertFalse(result.success)
        self.assertTrue(result.simulated)
        self.assertEqual(result.adapter_id, "log-only:email")

    def test_audit_callback_receives_hashed_tenant_only(self) -> None:
        register_log_only_defaults()
        bucket: list[dict] = []
        send_message(
            tenant_id="tenant-uuid-1",
            address=ChannelAddress(channel="push", address="device:1"),
            message=ChannelMessage(subject="x", body_text="x"),
            audit=bucket.append,
        )
        self.assertEqual(len(bucket), 1)
        self.assertNotIn("tenant-uuid-1", bucket[0]["tenant_id_hash"])
        self.assertEqual(len(bucket[0]["tenant_id_hash"]), 12)
