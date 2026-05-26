"""Depth tests for apps.communication.channel_adapter (batch 1509).

Complements test_channel_adapter_runtime.py (contract tests) with:

- cross-tenant isolation (hashed audit keys do not collide across tenants
  and do not contain the raw tenant_id)
- audit emission hygiene (no raw tenant_id, no body content)
- log emission hygiene (no PII, no raw address)
- fail-over behavior (registry rejects when no enabled adapter)
- registry state isolation (clear / re-register / select interleavings)
"""

from __future__ import annotations

import hashlib
import logging

from django.test import SimpleTestCase

from apps.communication.channel_adapter import (
    ChannelAdapterRegistry,
    ChannelAddress,
    ChannelMessage,
    ChannelUnavailableError,
    _LogOnlyAdapter,
    _hash_tenant,
    register_log_only_defaults,
    registry,
    send_message,
)


class ChannelAdapterDepthTests(SimpleTestCase):
    def setUp(self) -> None:
        registry().clear()
        register_log_only_defaults()

    def tearDown(self) -> None:
        registry().clear()

    def test_hash_tenant_is_stable_and_isolates_across_tenants(self) -> None:
        h1 = _hash_tenant("tenant-A")
        h2 = _hash_tenant("tenant-B")
        h1_again = _hash_tenant("tenant-A")
        self.assertEqual(h1, h1_again)
        self.assertNotEqual(h1, h2)
        self.assertEqual(len(h1), 12)
        self.assertEqual(len(h2), 12)

    def test_hash_tenant_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            _hash_tenant("")

    def test_audit_emission_omits_raw_tenant_id(self) -> None:
        bucket: list[dict] = []
        send_message(
            tenant_id="tenant-with-distinctive-slug-12345",
            address=ChannelAddress(channel="email", address="parent@example.test"),
            message=ChannelMessage(subject="x", body_text="x"),
            audit=bucket.append,
        )
        emitted = bucket[0]
        for key, value in emitted.items():
            self.assertNotIn(
                "tenant-with-distinctive-slug-12345",
                str(value),
                f"audit field {key} contains raw tenant slug",
            )

    def test_audit_emission_omits_message_body(self) -> None:
        bucket: list[dict] = []
        send_message(
            tenant_id="tenant-A",
            address=ChannelAddress(channel="email", address="parent@example.test"),
            message=ChannelMessage(subject="grade slipped", body_text="confidential note"),
            audit=bucket.append,
        )
        emitted_str = repr(bucket[0])
        self.assertNotIn("grade slipped", emitted_str)
        self.assertNotIn("confidential note", emitted_str)
        self.assertNotIn("parent@example.test", emitted_str)

    def test_cross_tenant_audit_keys_do_not_collide(self) -> None:
        bucket: list[dict] = []
        send_message(
            tenant_id="tenant-A",
            address=ChannelAddress(channel="email", address="a@example.test"),
            message=ChannelMessage(subject="x", body_text="x"),
            audit=bucket.append,
        )
        send_message(
            tenant_id="tenant-B",
            address=ChannelAddress(channel="email", address="b@example.test"),
            message=ChannelMessage(subject="x", body_text="x"),
            audit=bucket.append,
        )
        self.assertEqual(len(bucket), 2)
        self.assertNotEqual(bucket[0]["tenant_id_hash"], bucket[1]["tenant_id_hash"])

    def test_log_emission_uses_hashed_tenant_only(self) -> None:
        with self.assertLogs("apps.communication.channel_adapter", level="INFO") as cm:
            send_message(
                tenant_id="tenant-distinctive-XYZ",
                address=ChannelAddress(channel="email", address="parent@example.test"),
                message=ChannelMessage(subject="x", body_text="x"),
            )
        log_text = "\n".join(cm.output)
        self.assertNotIn("tenant-distinctive-XYZ", log_text)
        self.assertNotIn("parent@example.test", log_text)
        self.assertIn(_hash_tenant("tenant-distinctive-XYZ"), log_text)

    def test_registry_clear_isolates_state_between_calls(self) -> None:
        registry().clear()
        with self.assertRaises(ChannelUnavailableError):
            send_message(
                tenant_id="tenant-A",
                address=ChannelAddress(channel="email", address="a@example.test"),
                message=ChannelMessage(subject="x", body_text="x"),
            )

    def test_registry_select_skips_disabled_adapters(self) -> None:
        reg = ChannelAdapterRegistry()
        reg.register(_LogOnlyAdapter(channel="email", adapter_id="disabled-cheap", cost_rank=1, enabled=False))
        reg.register(_LogOnlyAdapter(channel="email", adapter_id="enabled-dear", cost_rank=10, enabled=True))
        entry = reg.select(preferred_channels=["email"])
        self.assertEqual(entry.adapter.adapter_id, "enabled-dear")

    def test_registry_select_falls_through_channels_in_order(self) -> None:
        reg = ChannelAdapterRegistry()
        reg.register(_LogOnlyAdapter(channel="sms", adapter_id="sms-only", cost_rank=5))
        entry = reg.select(preferred_channels=["email", "push", "sms"])
        self.assertEqual(entry.adapter.channel, "sms")

    def test_hash_tenant_does_not_use_md5_or_sha1(self) -> None:
        # Verify the implementation actually uses sha256 (not md5/sha1, which
        # are weaker and the no-mercy audit would flag).
        expected = hashlib.sha256(b"tenant-A").hexdigest()[:12]
        self.assertEqual(_hash_tenant("tenant-A"), expected)
