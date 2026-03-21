import hashlib
import hmac
import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School


@override_settings(ONEROSTER_WEBHOOK_SECRET="testsecret")
class OnerosterRosterWebhookTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="WH School",
            slug="wh-school",
            subdomain="wh-school",
            is_active=True,
        )
        self.client = Client()

    def _sign(self, body: bytes) -> str:
        return (
            "sha256="
            + hmac.new(b"testsecret", body, hashlib.sha256).hexdigest()
        )

    def test_rejects_without_config(self):
        with override_settings(ONEROSTER_WEBHOOK_SECRET=""):
            body = json.dumps(
            {"school_id": str(self.school.pk), "event": "x"}
        ).encode()
            r = self.client.post(
                reverse("api:oneroster-roster-webhook"),
                data=body,
                content_type="application/json",
            )
            self.assertEqual(r.status_code, 503)

    def test_accepts_valid_signature(self):
        body = json.dumps(
            {
                "school_id": str(self.school.pk),
                "event": "enrollment.changed",
            }
        ).encode()
        r = self.client.post(
            reverse("api:oneroster-roster-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_ROSTER_WEBHOOK_SIGNATURE=self._sign(body),
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertTrue(data.get("ok"))

    def test_rejects_bad_signature(self):
        body = json.dumps({"school_id": str(self.school.pk)}).encode()
        r = self.client.post(
            reverse("api:oneroster-roster-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_ROSTER_WEBHOOK_SIGNATURE="sha256=deadbeef",
        )
        self.assertEqual(r.status_code, 401)
