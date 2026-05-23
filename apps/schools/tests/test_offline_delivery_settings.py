from django.test import TestCase

from apps.schools.models import School
from apps.schools.offline_delivery_settings import (
    build_client_offline_config,
    get_offline_delivery_payload,
    set_offline_delivery_payload,
)


class OfflineDeliverySettingsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Offline Test", slug="offline-test")

    def test_round_trip(self):
        set_offline_delivery_payload(
            self.school,
            {"hub_base_url": "http://hub.local:8000", "max_queue_items": 120, "mesh_enabled": True},
        )
        self.school.save()
        payload = get_offline_delivery_payload(self.school)
        self.assertEqual(payload["hub_base_url"], "http://hub.local:8000")
        self.assertEqual(payload["max_queue_items"], 120)
        self.assertTrue(payload["mesh_enabled"])

    def test_client_config(self):
        set_offline_delivery_payload(self.school, {"max_queue_items": 200})
        cfg = build_client_offline_config(self.school)
        self.assertEqual(cfg["maxQueueItems"], 200)
