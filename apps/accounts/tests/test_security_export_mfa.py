from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserPasskey
from apps.accounts.views_security import _user_has_mfa


User = get_user_model()


class SecurityExportMfaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="passkey-user",
            email="passkey-user@example.com",
            password="password",
        )

    def test_user_has_mfa_accepts_passkey(self):
        UserPasskey.objects.create(
            user=self.user,
            name="Laptop passkey",
            credential_id="cred-passkey-user",
            public_key="public-key",
        )

        self.assertTrue(_user_has_mfa(self.user))

    def test_security_export_allows_passkey_only_user(self):
        UserPasskey.objects.create(
            user=self.user,
            name="Phone passkey",
            credential_id="cred-passkey-export",
            public_key="public-key",
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

        response = self.client.get(reverse("accounts:api_security_export_log"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("timestamp,event_type,ip_address,location,is_suspicious", response.content.decode("utf-8"))
