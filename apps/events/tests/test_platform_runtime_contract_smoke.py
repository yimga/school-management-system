"""Smoke import for unified platform event contract (cross-app visibility)."""

from __future__ import annotations

from django.test import SimpleTestCase


class PlatformRuntimeContractSmokeTests(SimpleTestCase):
    def test_contract_maps_row_fields(self):
        from apps.platform_runtime.event_contract import platform_event_to_contract

        class _Row:
            pk = 42
            event_type = "attendance_saved"
            tenant_id = "9"
            school_id = "9"
            payload = {
                "correlation_id": "corr-1",
                "actor": {"id": 3},
                "source": "api",
            }
            idempotency_key = "k1"
            created_at = None

        d = platform_event_to_contract(_Row())
        self.assertEqual(d["event_id"], 42)
        self.assertEqual(d["event_type"], "attendance_saved")
        self.assertEqual(d["tenant_id"], "9")
        self.assertEqual(d["school_id"], "9")
        self.assertEqual(d["correlation_id"], "corr-1")
        self.assertEqual(d["idempotency_key"], "k1")
        self.assertIn("payload", d)
