from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["*"])
class ClaimInviteHostBoundaryTests(TestCase):
    def test_claim_invite_requires_school_context(self):
        response = self.client.get(
            reverse("accounts:claim_invite"), HTTP_HOST="runmycampus.com"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("global_login_discovery"))
