"""Wave 4 — the authenticator entry shows RMC-<school>, never the raw username.

Owner spec: the MFA app should read "RMC-New High School", not "admin"/"nina".
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

U = get_user_model()


class MfaProvisioningLabelTests(TestCase):
    def _uri(self, school_name="New Test High", username="nina"):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        from apps.accounts.mfa_setup_flow import build_totp_provisioning_uri
        from apps.schools.models import School

        school = School.objects.create(
            name=school_name,
            subdomain="mfa-label-newtest",
            slug="mfa-label-newtest",
            is_active=True,
        )
        user = U.objects.create(username=username)
        device = TOTPDevice.objects.create(user=user, name="default", confirmed=False)
        req = RequestFactory().get("/authentication/mfa/setup/")
        req.school = school
        return build_totp_provisioning_uri(req, device)

    def test_label_is_tenant_product_not_username(self):
        uri = self._uri(school_name="New Test High", username="nina")
        self.assertNotIn("nina", uri)  # the username must not leak into the label
        self.assertIn("RMC-New", uri)  # issuer + label are RMC-<school>
        self.assertIn("issuer=RMC-New", uri)
