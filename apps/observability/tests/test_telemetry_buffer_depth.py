"""Depth tests for apps.observability.telemetry_buffer (batch 1509)."""

from __future__ import annotations

import hashlib
import hmac

from django.test import SimpleTestCase

from apps.observability.telemetry_buffer import (
    SCHEMA_VERSION,
    TelemetryBuffer,
    TelemetryBufferError,
    reset_default_buffer,
)


class TelemetryBufferDepthTests(SimpleTestCase):
    def setUp(self) -> None:
        reset_default_buffer()

    def tearDown(self) -> None:
        reset_default_buffer()

    def test_constructor_rejects_zero_capacity(self) -> None:
        with self.assertRaises(TelemetryBufferError):
            TelemetryBuffer(capacity=0)
        with self.assertRaises(TelemetryBufferError):
            TelemetryBuffer(capacity=-1)

    def test_record_rejects_empty_tenant_or_event(self) -> None:
        buf = TelemetryBuffer()
        with self.assertRaises(TelemetryBufferError):
            buf.record(tenant_id="", event_type="x", payload={})
        with self.assertRaises(TelemetryBufferError):
            buf.record(tenant_id="t", event_type="", payload={})

    def test_record_scrubs_sensitive_payload_keys(self) -> None:
        buf = TelemetryBuffer()
        packet = buf.record(
            tenant_id="tenant-A",
            event_type="audit",
            payload={
                "harmless": "value",
                "password": "should-not-survive",
                "api_key": "should-not-survive",
                "token": "should-not-survive",
            },
        )
        self.assertIn("harmless", packet.payload)
        self.assertNotIn("password", packet.payload)
        self.assertNotIn("api_key", packet.payload)
        self.assertNotIn("token", packet.payload)

    def test_record_scrubs_nested_payload(self) -> None:
        buf = TelemetryBuffer()
        packet = buf.record(
            tenant_id="tenant-A",
            event_type="audit",
            payload={"nested": {"secret": "x", "ok": "y"}},
        )
        self.assertNotIn("secret", packet.payload["nested"])
        self.assertEqual(packet.payload["nested"]["ok"], "y")

    def test_record_uses_hashed_tenant_id(self) -> None:
        buf = TelemetryBuffer()
        packet = buf.record(
            tenant_id="tenant-distinctive-XYZ",
            event_type="audit",
        )
        self.assertNotIn("tenant-distinctive-XYZ", packet.tenant_id_hash)
        self.assertEqual(len(packet.tenant_id_hash), 12)

    def test_capacity_overflow_drops_oldest(self) -> None:
        buf = TelemetryBuffer(capacity=3)
        ids = []
        for i in range(5):
            packet = buf.record(
                tenant_id="tenant-A",
                event_type=f"event-{i}",
                payload={"i": i},
            )
            ids.append(packet.packet_id)
        self.assertEqual(len(buf), 3)
        remaining_events = [p.event_type for p in buf.peek()]
        self.assertEqual(remaining_events, ["event-2", "event-3", "event-4"])

    def test_flush_returns_canonical_body_and_clears_buffer(self) -> None:
        buf = TelemetryBuffer()
        for i in range(3):
            buf.record(tenant_id="tenant-A", event_type=f"e{i}", payload={"i": i})
        body = buf.flush()
        self.assertEqual(body["packet_count"], 3)
        self.assertEqual(body["schema_version"], SCHEMA_VERSION)
        self.assertIn("flush_checksum", body)
        self.assertEqual(len(buf), 0)

    def test_flush_signature_uses_correct_secret(self) -> None:
        buf = TelemetryBuffer()
        buf.record(tenant_id="tenant-A", event_type="x")
        body = buf.flush(sign_with=b"shared-secret")
        self.assertIn("signature", body)
        expected = hmac.new(
            b"shared-secret",
            ('{"flush_checksum":"' + body["flush_checksum"] + '"}').encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(body["signature"], expected)

    def test_flush_without_signing_key_omits_signature(self) -> None:
        buf = TelemetryBuffer()
        buf.record(tenant_id="tenant-A", event_type="x")
        body = buf.flush()
        self.assertNotIn("signature", body)

    def test_cross_tenant_packets_have_distinct_hashes(self) -> None:
        buf = TelemetryBuffer()
        p_a = buf.record(tenant_id="tenant-A", event_type="x")
        p_b = buf.record(tenant_id="tenant-B", event_type="x")
        self.assertNotEqual(p_a.tenant_id_hash, p_b.tenant_id_hash)

    def test_log_emission_omits_payload(self) -> None:
        buf = TelemetryBuffer()
        buf.record(
            tenant_id="tenant-A",
            event_type="audit",
            payload={"confidential_field_XYZ": "secret-payload-value"},
        )
        with self.assertLogs("apps.observability.telemetry_buffer", level="INFO") as cm:
            buf.flush()
        log_text = "\n".join(cm.output)
        self.assertNotIn("secret-payload-value", log_text)
        self.assertNotIn("confidential_field_XYZ", log_text)
