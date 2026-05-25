"""Offline queue contract runtime tests (batch 1506 audit closure)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability.telemetry_buffer import TelemetryBuffer
from apps.sync_engine.tenant_manifest_compiler import compile_manifest


class OfflineQueueContractRuntimeTests(SimpleTestCase):
    def test_manifest_declares_offline_queue_cache_hint(self) -> None:
        m = compile_manifest(
            tenant_id="t",
            pwa_cache_hints={
                "offline_queue_db": "rmc-offline-queue",
                "stores": ["request_queue", "attempted_replays", "checkpoint"],
            },
        )
        self.assertEqual(m.pwa_cache_hints["offline_queue_db"], "rmc-offline-queue")
        self.assertIn("checkpoint", m.pwa_cache_hints["stores"])

    def test_offline_buffer_survives_capacity_cap(self) -> None:
        buf = TelemetryBuffer(capacity=3)
        for i in range(10):
            buf.record(tenant_id="t", event_type=f"event-{i}")
        self.assertEqual(len(buf), 3)
        # FIFO: last three should remain
        events = [p.event_type for p in buf.peek()]
        self.assertEqual(events, ["event-7", "event-8", "event-9"])

    def test_offline_buffer_flush_produces_replay_payload(self) -> None:
        buf = TelemetryBuffer()
        buf.record(tenant_id="t", event_type="login", payload={"actor": "anon"})
        buf.record(tenant_id="t", event_type="sync.attempt")
        out = buf.flush(sign_with=b"k")
        self.assertEqual(out["packet_count"], 2)
        self.assertEqual(len(buf), 0)
        self.assertIn("signature", out)

    def test_manifest_excludes_secret_keys_from_cache_hints(self) -> None:
        m = compile_manifest(
            tenant_id="t",
            pwa_cache_hints={"offline_queue_db": "db", "api_key": "leak", "secret": "leak"},
        )
        self.assertNotIn("api_key", m.pwa_cache_hints)
        self.assertNotIn("secret", m.pwa_cache_hints)

    def test_buffer_record_returns_packet_with_deterministic_checksum(self) -> None:
        buf = TelemetryBuffer()
        p1 = buf.record(tenant_id="t", event_type="x", payload={"a": 1})
        p2 = buf.record(tenant_id="t", event_type="x", payload={"a": 1})
        self.assertEqual(p1.checksum, p2.checksum)
        self.assertNotEqual(p1.packet_id, p2.packet_id)
