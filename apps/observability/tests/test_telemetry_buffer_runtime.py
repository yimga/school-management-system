"""Runtime tests for apps.observability.telemetry_buffer (batch 1493)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability.telemetry_buffer import (
    SCHEMA_VERSION,
    TelemetryBuffer,
    TelemetryBufferError,
)


class TelemetryBufferRuntimeTests(SimpleTestCase):
    def test_record_returns_packet_with_hashed_tenant(self) -> None:
        buf = TelemetryBuffer()
        p = buf.record(tenant_id="tenant-x", event_type="heartbeat", payload={"k": 1})
        self.assertEqual(p.schema_version, SCHEMA_VERSION)
        self.assertNotEqual(p.tenant_id_hash, "tenant-x")
        self.assertEqual(p.payload, {"k": 1})
        self.assertEqual(len(p.checksum), 64)

    def test_sensitive_payload_keys_are_dropped(self) -> None:
        buf = TelemetryBuffer()
        p = buf.record(
            tenant_id="t1",
            event_type="login",
            payload={"event_kind": "login", "password": "x", "raw_prompt": "y"},
        )
        self.assertIn("event_kind", p.payload)
        self.assertNotIn("password", p.payload)
        self.assertNotIn("raw_prompt", p.payload)

    def test_capacity_enforces_fifo_drop(self) -> None:
        buf = TelemetryBuffer(capacity=2)
        buf.record(tenant_id="t", event_type="a")
        buf.record(tenant_id="t", event_type="b")
        buf.record(tenant_id="t", event_type="c")
        kinds = [p.event_type for p in buf.peek()]
        self.assertEqual(kinds, ["b", "c"])

    def test_flush_emits_signed_payload_when_secret_present(self) -> None:
        buf = TelemetryBuffer()
        buf.record(tenant_id="t", event_type="a")
        flushed = buf.flush(sign_with=b"shared-secret")
        self.assertEqual(flushed["packet_count"], 1)
        self.assertIn("flush_checksum", flushed)
        self.assertIn("signature", flushed)
        self.assertEqual(len(buf), 0)

    def test_missing_tenant_id_raises(self) -> None:
        buf = TelemetryBuffer()
        with self.assertRaises(TelemetryBufferError):
            buf.record(tenant_id="", event_type="x")
