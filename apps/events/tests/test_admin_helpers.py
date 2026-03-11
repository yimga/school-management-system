from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from apps.events.admin import DomainEventAdmin
from apps.events.models import DomainEvent


class EventAdminHelperTests(SimpleTestCase):
    def test_payload_preview_falls_back_for_non_json_payload(self):
        admin = DomainEventAdmin(model=DomainEvent, admin_site=AdminSite())
        obj = type("Obj", (), {"payload": {"bad": {1, 2, 3}}})()

        preview = admin.payload_preview(obj)

        self.assertIn("bad", preview)
