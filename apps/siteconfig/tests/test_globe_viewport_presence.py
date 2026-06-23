"""Globe viewport presence tests (W17)."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.siteconfig.globe_viewport_presence import (
    compute_region_hash,
    count_globe_viewport_viewers,
    heartbeat_globe_viewport,
)


class GlobeViewportPresenceTests(TestCase):
    def test_region_hash_stable(self):
        a = compute_region_hash(region="West Africa")
        b = compute_region_hash(region="West Africa")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 12)

    def test_heartbeat_and_count(self):
        region = compute_region_hash(region="Europe")
        heartbeat_globe_viewport(user_id=101, region_hash=region)
        heartbeat_globe_viewport(user_id=102, region_hash=region)
        self.assertEqual(count_globe_viewport_viewers(region_hash=region), 2)
        self.assertEqual(
            count_globe_viewport_viewers(region_hash=region, exclude_user_id=101),
            1,
        )


class GlobeViewportPresenceApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="globe_presence_admin",
            email="gp@example.com",
            password="Test1234!",
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("super:api_operator_fleet_globe_presence")

    def test_get_presence_count(self):
        resp = self.client.get(self.url, {"region": "West Africa"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("others_viewing", data)
        self.assertIn("heartbeat_seconds", data)

    def test_post_heartbeat(self):
        resp = self.client.post(self.url, {"region": "West Africa"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("viewers", resp.json())
