from django.test import TestCase

from apps.schools.email_delivery_settings import (
    get_email_delivery_payload,
    set_email_delivery_payload,
)
from apps.schools.models import School


class EmailDeliverySettingsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Email Test", slug="email-test")

    def test_password_never_in_get_payload(self):
        set_email_delivery_payload(
            self.school,
            {"enabled": True, "host": "smtp.example.com"},
            password_encrypted_b64="encrypted-token",
        )
        payload = get_email_delivery_payload(self.school)
        self.assertTrue(payload["has_password"])
        self.assertNotIn("host_password", payload)
        self.assertNotIn("host_password_encrypted_b64", payload)
