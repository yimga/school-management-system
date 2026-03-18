from django.test import TestCase

from apps.platform_runtime.events import emit_platform_event
from apps.platform_runtime.models import PlatformEventLog


class PlatformEventLogTests(TestCase):
    def test_emit_persists_catalog_event(self):
        emit_platform_event(
            "package_applied",
            {"package_id": "pkg-1", "package_type": "blueprint", "school_id": "abc"},
            school_id="school-uuid-1",
            idempotency_key="idem-1",
        )
        row = PlatformEventLog.objects.filter(event_type="package_applied").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.idempotency_key, "idem-1")
        self.assertIn("package_id", row.payload)
