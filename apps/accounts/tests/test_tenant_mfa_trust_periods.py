"""Tenant MFA enrollment is mandatory; post-verification device trust is bounded."""

from __future__ import annotations

import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.mfa_device_trust import (
    DEVICE_TRUST_COOKIE,
    device_trust_allowed_days,
    device_trust_default_days,
    device_trust_valid,
    issue_device_trust_token,
    set_device_trust_cookie,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


def _current_totp(device: TOTPDevice) -> str:
    code = totp(
        device.bin_key,
        step=device.step,
        t0=device.t0,
        digits=device.digits,
        drift=device.drift,
    )
    return str(code).zfill(device.digits)


@override_settings(
    MFA_DEVICE_TRUST_DAYS=30,
    MFA_DEVICE_TRUST_ALLOWED_DAYS="1,7,14,30",
    MFA_DEVICE_TRUST_DEFAULT_DAYS=14,
)
class DeviceTrustPeriodTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="bounded-trust",
            email="bounded-trust@example.com",
            password="MfaTrust123!",
        )

    def _request(self, token):
        request = self.factory.get("/")
        request.COOKIES[DEVICE_TRUST_COOKIE] = token
        return request

    def test_default_periods_are_explicit_and_bounded(self):
        self.assertEqual(device_trust_allowed_days(), (1, 7, 14, 30))
        self.assertEqual(device_trust_default_days(), 14)

    def test_selected_period_controls_cookie_lifetime(self):
        from django.http import HttpResponse

        response = HttpResponse()
        set_device_trust_cookie(
            response, self.user, self.factory.get("/"), trust_days=7
        )
        self.assertEqual(
            int(response.cookies[DEVICE_TRUST_COOKIE]["max-age"]),
            7 * 24 * 60 * 60,
        )

    def test_arbitrary_client_period_cannot_extend_trust(self):
        from django.http import HttpResponse

        response = HttpResponse()
        set_device_trust_cookie(
            response, self.user, self.factory.get("/"), trust_days=3650
        )
        self.assertEqual(
            int(response.cookies[DEVICE_TRUST_COOKIE]["max-age"]),
            14 * 24 * 60 * 60,
        )

    def test_selected_period_expires_even_inside_platform_cap(self):
        now = int(time.time())
        with patch("apps.accounts.mfa_device_trust.time.time", return_value=now):
            token = issue_device_trust_token(self.user, trust_days=7)
        self.assertTrue(device_trust_valid(self._request(token), self.user))
        with patch(
            "apps.accounts.mfa_device_trust.time.time",
            return_value=now + (8 * 24 * 60 * 60),
        ):
            self.assertFalse(device_trust_valid(self._request(token), self.user))


@override_settings(
    RATELIMIT_ENABLE=False,
    LOGIN_POW_ENABLED=False,
    LOGIN_MIN_FORM_SECONDS=0,
    ALLOWED_HOSTS=["*", "trust-school.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
)
class TenantLoginTrustFlowTests(TestCase):
    host = "trust-school.runmycampus.com"

    def setUp(self):
        self.user = User.objects.create_user(
            username="tenant-owner@example.com",
            email="tenant-owner@example.com",
            password="MfaTrust123!",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.school = School.objects.create(
            name="Trust School",
            slug="trust-school",
            subdomain="trust-school",
            is_active=True,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
        )
        self.device = TOTPDevice.objects.create(
            user=self.user, name="default", confirmed=True
        )

    def test_password_mfa_then_selected_trust_allows_next_login(self):
        client = Client(HTTP_HOST=self.host)
        first = client.post(
            reverse("accounts:login"),
            {
                "username": self.user.username,
                "password": "MfaTrust123!",
            },
        )
        self.assertEqual(first.status_code, 302)
        self.assertIn("/authentication/mfa/verify", first.url)

        verified = client.post(
            reverse("accounts:mfa_verify"),
            {
                "token": _current_totp(self.device),
                "remember_device": "1",
                "trust_days": "7",
            },
        )
        self.assertEqual(verified.status_code, 302)
        self.assertIn(DEVICE_TRUST_COOKIE, verified.cookies)
        self.assertEqual(
            int(verified.cookies[DEVICE_TRUST_COOKIE]["max-age"]),
            7 * 24 * 60 * 60,
        )

        # A genuinely new login session with only the signed trust cookie should
        # authenticate normally instead of returning to the MFA checkpoint.
        fresh = Client(HTTP_HOST=self.host)
        fresh.cookies[DEVICE_TRUST_COOKIE] = client.cookies[
            DEVICE_TRUST_COOKIE
        ].value
        second = fresh.post(
            reverse("accounts:login"),
            {
                "username": self.user.username,
                "password": "MfaTrust123!",
            },
        )
        self.assertEqual(second.status_code, 302)
        self.assertNotIn("/authentication/mfa/verify", second.url)

    def test_verify_page_offers_real_bounded_periods(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("accounts:mfa_verify"),
            HTTP_HOST=self.host,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="trust_days"')
        for days in (1, 7, 14, 30):
            self.assertContains(response, f'value="{days}"')
