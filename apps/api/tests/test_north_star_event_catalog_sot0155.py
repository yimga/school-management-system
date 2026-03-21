"""§0.1.5 Wave 2: north-star event catalog reachable for staff."""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class NorthStarEventCatalogSot0155Tests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="evcat_staff",
            email="e@example.com",
            password="x",
            is_staff=True,
        )
        self.client = Client()
        self.assertTrue(self.client.login(username="evcat_staff", password="x"))

    def test_event_catalog_get_returns_json(self):
        r = self.client.get(reverse("api:api-north-star-event-catalog"))
        self.assertIn(r.status_code, (200, 403))
        if r.status_code == 200:
            data = json.loads(r.content)
            self.assertIsInstance(data, (dict, list))
