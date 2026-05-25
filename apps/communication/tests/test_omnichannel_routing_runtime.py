"""Omnichannel routing runtime tests (batch 1506 audit closure)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.communication.channel_adapter import (
    ChannelAdapterRegistry,
    ChannelAddress,
    ChannelMessage,
    ChannelUnavailableError,
    _LogOnlyAdapter,
    register_log_only_defaults,
    registry,
    send_message,
)


class OmnichannelRoutingRuntimeTests(SimpleTestCase):
    def setUp(self) -> None:
        registry().clear()

    def test_router_prefers_higher_reliability(self) -> None:
        reg = ChannelAdapterRegistry()
        cheap_unreliable = _LogOnlyAdapter(channel="sms", adapter_id="cheap-flaky", cost_rank=1)
        dear_solid = _LogOnlyAdapter(channel="sms", adapter_id="dear-solid", cost_rank=20)
        reg.register(cheap_unreliable, reliability=0.4)
        reg.register(dear_solid, reliability=0.99)
        entry = reg.select(preferred_channels=["sms"])
        self.assertEqual(entry.adapter.adapter_id, "dear-solid")

    def test_router_falls_back_to_secondary_channel(self) -> None:
        reg = ChannelAdapterRegistry()
        reg.register(_LogOnlyAdapter(channel="email", adapter_id="email-1", cost_rank=5))
        # sms not registered → preferring sms then email picks email
        entry = reg.select(preferred_channels=["sms", "email"])
        self.assertEqual(entry.adapter.channel, "email")

    def test_router_raises_when_all_disabled(self) -> None:
        reg = ChannelAdapterRegistry()
        reg.register(_LogOnlyAdapter(channel="email", adapter_id="x"), enabled=False)
        with self.assertRaises(ChannelUnavailableError):
            reg.select(preferred_channels=["email"])

    def test_send_message_propagates_adapter_audit(self) -> None:
        register_log_only_defaults()
        events: list[dict] = []
        result = send_message(
            tenant_id="t1",
            address=ChannelAddress(channel="email", address="parent@x"),
            message=ChannelMessage(subject="x", body_text="y"),
            preferred_channels=["whatsapp", "email"],
            audit=events.append,
        )
        self.assertTrue(result.success)
        # Whichever channel was selected from the preferred list must surface in audit.
        self.assertEqual(events[0]["channel"], result.channel)
        self.assertIn(result.channel, {"whatsapp", "email"})

    def test_router_picks_in_order_when_reliability_tied(self) -> None:
        reg = ChannelAdapterRegistry()
        reg.register(_LogOnlyAdapter(channel="push", adapter_id="a", cost_rank=3), reliability=0.9)
        reg.register(_LogOnlyAdapter(channel="push", adapter_id="b", cost_rank=3), reliability=0.9)
        entry = reg.select(preferred_channels=["push"])
        self.assertEqual(entry.adapter.adapter_id, "a")
