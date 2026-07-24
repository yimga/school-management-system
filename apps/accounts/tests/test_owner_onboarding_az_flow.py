"""A–Z owner onboarding: account → brand → mandatory MFA → provision kick.

Proves the new-school path that was stuck in production:
- wizard cannot complete without a confirmed MFA device
- unconfirmed draft devices do not count as enrolled
- MFA verify without a confirmed device routes to setup (not login loop)
- school step queues provisioning via ``complete_provisioning_for_school``
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.onboarding_tokens import activation_token_generator
from apps.schools.models import School, SchoolMembership

STRONG_PW = "Zaq12wsx!RmC9"
User = get_user_model()


@override_settings(
    RATELIMIT_ENABLE=False,
    ALLOWED_HOSTS=["*", "testserver", "az-cedar.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    LOGIN_POW_ENABLED=False,
    LOGIN_MIN_FORM_SECONDS=0,
)
class OwnerOnboardingAZFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="az-owner",
            email="az-owner@cedar.test",
            role=User.Role.ADMIN,
        )
        self.user.set_unusable_password()
        self.user.save()
        self.school = School.objects.create(
            name="AZ Cedar",
            slug="az-cedar",
            subdomain="az-cedar",
            is_active=False,
            settings={},
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
        )

    def _account_url(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = activation_token_generator.make_token(self.user)
        return reverse(
            "accounts:owner_onboarding_account",
            kwargs={"uidb64": uid, "token": token},
        )

    def test_az_password_brand_cannot_waive_first_mfa(self):
        url = self._account_url()
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302)
        sentinel = r.url
        self.client.get(sentinel)
        r2 = self.client.post(
            sentinel,
            {
                "first_name": "Ada",
                "last_name": "Owner",
                "new_password1": STRONG_PW,
                "new_password2": STRONG_PW,
            },
        )
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r2.url, reverse("accounts:owner_onboarding_school"))

        with mock.patch(
            "apps.accounts.views_owner_onboarding._finish_provisioning_before_done"
        ):
            r3 = self.client.post(
                reverse("accounts:owner_onboarding_school"),
                {"school_name": "AZ Cedar Academy", "primary_color": "#224466"},
            )
        self.assertEqual(r3.status_code, 302)
        self.assertEqual(r3.url, reverse("accounts:owner_onboarding_mfa"))

        r4 = self.client.get(reverse("accounts:owner_onboarding_mfa"))
        self.assertEqual(r4.status_code, 200)
        self.assertContains(r4, "This step is required")
        self.assertNotContains(r4, "Continue without MFA")

        # A forged legacy waiver POST must not advance the wizard.
        r5 = self.client.post(
            reverse("accounts:owner_onboarding_mfa"),
            {"waive_mfa": "1"},
        )
        self.assertEqual(r5.status_code, 200)
        self.school.refresh_from_db()
        state = self.school.settings["owner_onboarding"]
        self.assertEqual(state["step"], "mfa")
        self.assertFalse(state.get("completed", False))
        self.assertFalse(state.get("mfa_waived", False))

    def test_school_step_kicks_complete_provisioning_for_school(self):
        self.client.force_login(
            self.user, backend="django.contrib.auth.backends.ModelBackend"
        )
        with mock.patch(
            "apps.schools.tasks.complete_provisioning_for_school",
            return_value={"queued": True, "is_active": False},
        ) as complete:
            r = self.client.post(
                reverse("accounts:owner_onboarding_school"),
                {"school_name": "AZ Cedar", "primary_color": "#112233"},
            )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("accounts:owner_onboarding_mfa"))
        complete.assert_called_once_with(
            str(self.school.pk), contact_email=self.user.email
        )

    def test_mfa_verify_without_confirmed_device_goes_to_setup(self):
        TOTPDevice.objects.create(user=self.user, name="draft", confirmed=False)
        self.client.force_login(
            self.user, backend="django.contrib.auth.backends.ModelBackend"
        )
        r = self.client.get(reverse("accounts:mfa_verify"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/mfa/setup", r.url)
