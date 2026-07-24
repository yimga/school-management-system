"""New-school owner: create password → set up MFA → login is ready, no re-wall.

Enrollment is mandatory; device trust is the optional part. This locks the
promise behind it: having just proved possession of their
device, they are handed straight to their dashboard and their NEXT login from the
same browser is not a fresh MFA wall.

Four fixes are pinned here, each with a must-FIRE assertion (a test that would
pass against the old code proves nothing):

* Fix A — the durable "trust this device" cookie is scoped to the session's own
  domain, so it actually reaches the tenant subdomain instead of being host-only.
* Fix B — confirming a TOTP during onboarding (with the box left ticked) issues
  that durable cookie + the session window, so the hand-off doesn't re-challenge.
* Fix C — the done-page "go to your dashboard" CTA reaches the dashboard once MFA
  is satisfied, instead of looping back to the MFA step.
* Fix D — ``resolve_post_login_mfa_redirect`` honours the trust cookie, so a
  trusted device is not hard-prompted for a code on its very next login.
"""

from __future__ import annotations

from unittest import mock

from importlib import import_module

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.mfa_device_trust import (
    DEVICE_TRUST_COOKIE,
    issue_device_trust_token,
    set_device_trust_cookie,
)
from apps.accounts.onboarding_tokens import activation_token_generator
from apps.schools.models import School, SchoolMembership

STRONG_PW = "Zaq12wsx!RmC9"
User = get_user_model()


def _fresh_session():
    """A real SessionStore (supports ``.modified``, unlike a bare dict)."""
    return import_module(django_settings.SESSION_ENGINE).SessionStore()


def _current_totp(device: TOTPDevice) -> str:
    """A valid code for ``device`` right now (django_otp's own algorithm)."""
    code = totp(
        device.bin_key,
        step=device.step,
        t0=device.t0,
        digits=device.digits,
        drift=device.drift,
    )
    return str(code).zfill(device.digits)


class DeviceTrustCookieDomainTests(TestCase):
    """Fix A: the trust cookie must carry as far as the session it backs."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="dom-user", email="d@example.com", password="pass12345678"
        )

    @override_settings(SESSION_COOKIE_DOMAIN=".runmycampus.com")
    def test_cookie_domain_matches_session_domain(self):
        response = HttpResponse()
        set_device_trust_cookie(response, self.user, self.factory.get("/"))
        cookie = response.cookies[DEVICE_TRUST_COOKIE]
        self.assertEqual(
            cookie["domain"],
            ".runmycampus.com",
            "host-only trust cookie is absent on the tenant subdomain — the "
            "durability guarantee silently fails across hosts",
        )

    @override_settings(SESSION_COOKIE_DOMAIN=None)
    def test_cookie_is_host_only_when_session_is(self):
        response = HttpResponse()
        set_device_trust_cookie(response, self.user, self.factory.get("/"))
        # No broader than the session: unset in dev → host-only, unchanged.
        self.assertEqual(response.cookies[DEVICE_TRUST_COOKIE]["domain"], "")


class PostLoginTrustCookieTests(TestCase):
    """Fix D: a trusted device is not re-prompted for a code on re-login."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="relogin-user",
            email="r@example.com",
            password="pass12345678",
            role=User.Role.ADMIN,
        )
        # A confirmed device — otherwise there is nothing to be prompted for.
        TOTPDevice.objects.create(user=self.user, name="default", confirmed=True)

    def _request(self, *, with_cookie: bool):
        request = self.factory.get("/authentication/backend/")
        request.user = self.user
        request.session = _fresh_session()
        request.school = None
        if with_cookie:
            request.COOKIES[DEVICE_TRUST_COOKIE] = issue_device_trust_token(self.user)
        return request

    def test_valid_trust_cookie_skips_the_verify_wall_on_relogin(self):
        from apps.accounts.post_login_mfa import resolve_post_login_mfa_redirect

        request = self._request(with_cookie=True)
        result = resolve_post_login_mfa_redirect(request, self.user)
        self.assertIsNone(
            result, "a trusted device was still walled to /mfa/verify/ on re-login"
        )
        self.assertTrue(request.session.get("mfa_verified"))

    def test_without_cookie_a_device_holder_is_still_challenged(self):
        from apps.accounts.post_login_mfa import resolve_post_login_mfa_redirect

        request = self._request(with_cookie=False)
        result = resolve_post_login_mfa_redirect(request, self.user)
        self.assertIsNotNone(result, "device-holder must be challenged with no trust")
        self.assertIn("/mfa/verify", result["Location"])


@override_settings(
    RATELIMIT_ENABLE=False,
    ALLOWED_HOSTS=["*", "testserver", "ready-oak.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_COOKIE_DOMAIN=".runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    LOGIN_POW_ENABLED=False,
    LOGIN_MIN_FORM_SECONDS=0,
)
class OwnerOnboardingEnrollReadyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ready-owner",
            email="ready-owner@oak.test",
            role=User.Role.ADMIN,
        )
        self.user.set_unusable_password()
        self.user.save()
        self.school = School.objects.create(
            name="Ready Oak",
            slug="ready-oak",
            subdomain="ready-oak",
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

    def _set_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = activation_token_generator.make_token(self.user)
        url = reverse(
            "accounts:owner_onboarding_account", kwargs={"uidb64": uid, "token": token}
        )
        sentinel = self.client.get(url).url  # 302 → set-password sentinel
        self.client.get(sentinel)  # load the form (seeds the session token)
        resp = self.client.post(
            sentinel,
            {
                "first_name": "Ola",
                "last_name": "Owner",
                "new_password1": STRONG_PW,
                "new_password2": STRONG_PW,
            },
        )
        self.assertEqual(resp.url, reverse("accounts:owner_onboarding_school"))

    def _confirm_brand(self):
        with mock.patch(
            "apps.accounts.views_owner_onboarding._finish_provisioning_before_done"
        ):
            resp = self.client.post(
                reverse("accounts:owner_onboarding_school"),
                {"school_name": "Ready Oak Academy", "primary_color": "#0a5c36"},
            )
        # No confirmed device yet → routed into the MFA step.
        self.assertEqual(resp.url, reverse("accounts:owner_onboarding_mfa"))

    def _enroll_mfa(self, *, remember: bool, trust_days=None):
        # Show the QR (creates the unconfirmed draft device).
        self.client.post(reverse("accounts:owner_onboarding_mfa"), {"enable_mfa": "1"})
        device = TOTPDevice.objects.get(user=self.user, name="default")
        self.assertFalse(device.confirmed)
        data = {
            "verify_token": "1",
            "device_id": device.id,
            "token": _current_totp(device),
        }
        if remember:
            data["remember_device"] = "1"
        if trust_days is not None:
            data["trust_days"] = str(trust_days)
        return self.client.post(reverse("accounts:owner_onboarding_mfa"), data)

    def test_enroll_confirms_device_trusts_it_and_reaches_done(self):
        self._set_password()
        self._confirm_brand()
        resp = self._enroll_mfa(remember=True, trust_days=7)

        # Device is confirmed — real proof-of-possession, not a draft.
        device = TOTPDevice.objects.get(user=self.user, name="default")
        self.assertTrue(device.confirmed)

        # Fix B: the enroll hand-off carries durable verified state forward.
        self.assertEqual(resp.url, reverse("accounts:owner_onboarding_done"))
        self.assertIn(
            DEVICE_TRUST_COOKIE,
            resp.cookies,
            "enrolling with the box ticked did not trust the device",
        )
        # Fix A: and that cookie is scoped to reach the tenant subdomain.
        self.assertEqual(resp.cookies[DEVICE_TRUST_COOKIE]["domain"], ".runmycampus.com")
        self.assertEqual(
            int(resp.cookies[DEVICE_TRUST_COOKIE]["max-age"]),
            7 * 24 * 60 * 60,
        )
        self.assertTrue(self.client.session.get("mfa_verified"))
        self.assertTrue(self.client.session.get("mfa_verified_until"))

    def test_first_enrollment_does_not_preselect_device_trust(self):
        self._set_password()
        self._confirm_brand()
        resp = self.client.post(
            reverse("accounts:owner_onboarding_mfa"), {"enable_mfa": "1"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="trust_days"')
        self.assertNotContains(
            resp,
            'id="mfa-setup-remember-device" name="remember_device" value="1" checked',
        )

    def test_enroll_without_remember_does_not_silently_trust(self):
        self._set_password()
        self._confirm_brand()
        resp = self._enroll_mfa(remember=False)
        self.assertEqual(resp.url, reverse("accounts:owner_onboarding_done"))
        self.assertNotIn(
            DEVICE_TRUST_COOKIE,
            resp.cookies,
            "unticking the box must not trust a shared machine",
        )

    def test_done_cta_reaches_dashboard_after_enrolling(self):
        self._set_password()
        self._confirm_brand()
        self._enroll_mfa(remember=True)
        with mock.patch(
            "apps.schools.provision_email_urls.tenant_subdomain_host_exists",
            return_value=False,
        ):
            resp = self.client.get(reverse("accounts:owner_onboarding_done"))
        self.assertEqual(resp.status_code, 200)
        # Fix C: an enrolled owner's primary CTA is NOT the MFA step.
        cta = resp.context["dashboard_href"]
        self.assertNotEqual(cta, reverse("accounts:owner_onboarding_mfa"))
        self.school.refresh_from_db()
        self.assertTrue(self.school.settings["owner_onboarding"]["completed"])

    def test_next_login_from_trusted_browser_is_not_re_walled(self):
        """The whole point: enroll → next login is ready, no code re-prompt."""
        self._set_password()
        self._confirm_brand()
        self._enroll_mfa(remember=True)

        # Simulate a genuinely fresh login: drop the server session but keep the
        # browser's durable trust cookie (exactly what a re-login looks like).
        trust_cookie = self.client.cookies[DEVICE_TRUST_COOKIE].value
        self.client.logout()
        self.client.cookies[DEVICE_TRUST_COOKIE] = trust_cookie

        from apps.accounts.post_login_mfa import resolve_post_login_mfa_redirect

        # Reload: the password was set DURING the flow, so the setUp object's
        # session-auth-hash (still on the unusable password) would not match the
        # fingerprint baked into the cookie at enroll time.
        self.user.refresh_from_db()
        request = RequestFactory().get("/authentication/backend/")
        request.user = self.user
        request.session = _fresh_session()
        request.school = None
        request.COOKIES[DEVICE_TRUST_COOKIE] = trust_cookie
        self.assertIsNone(
            resolve_post_login_mfa_redirect(request, self.user),
            "a device trusted during onboarding was re-walled on next login",
        )
