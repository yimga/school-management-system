"""Tests for the resend-signup-verification flow (2026-06-06).

Covers: enumeration-safety, abuse throttling, token rotation + expiry refresh,
and the GET form render. The resend path lets a user whose 2-day verification
link expired get a fresh one instead of re-running signup.
"""

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.schools.models import School, SignupVerification
from apps.test_utils.tenant_hosts import HOST_ROUTED_SETTINGS, PUBLIC_HOST


class ResendVerificationTests(TestCase):
    def setUp(self):
        cache.clear()  # cooldown/daily-cap counters are cache-backed

    def test_public_urlconf_exposes_resend_and_verify_signup_error_page(self):
        """runmycampus.com uses config.public_urls — verify-signup must reverse resend."""
        from django.urls import reverse

        reverse("resend_signup_verification", urlconf="config.public_urls")
        # ROOT_URLCONF alone would not put this request on the public surface:
        # UrlConfSwitcherMiddleware sets request.urlconf from the Host header, and
        # the default test host (testserver) is classified local -> config.urls.
        with self.settings(ROOT_URLCONF="config.public_urls", **HOST_ROUTED_SETTINGS):
            resp = self.client.get(
                reverse("verify_signup") + "?token=00000000-0000-0000-0000-000000000000",
                HTTP_HOST=PUBLIC_HOST,
            )
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Resend my verification link", status_code=400)

    def _pending(self, email="owner@cedar.test", expired=False):
        school = School.objects.create(
            name="Cedar School",
            slug="cedar",
            subdomain="cedar",
            is_active=False,
            country_code="US",
            settings={},
        )
        return SignupVerification.objects.create(
            school=school,
            email=email,
            expires_at=timezone.now() + timedelta(days=-1 if expired else 2),
        )

    def test_get_renders_form(self):
        resp = self.client.get(reverse("resend_signup_verification"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Resend verification link")
        self.assertContains(resp, 'name="email"')

    def test_invalid_email_is_400(self):
        resp = self.client.post(
            reverse("resend_signup_verification"), {"email": "not-an-email"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_unknown_email_is_enumeration_safe(self):
        # No matching signup -> still the generic success message, no crash.
        with mock.patch(
            "apps.schools.signup_views._send_signup_verification_email"
        ) as send:
            resp = self.client.post(
                reverse("resend_signup_verification"),
                {"email": "nobody-xyz@example.com"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "pending school signup")
        send.assert_not_called()

    def test_found_pending_rotates_token_extends_expiry_and_resends(self):
        sv = self._pending(expired=True)
        old_token = sv.token
        old_expiry = sv.expires_at
        with mock.patch(
            "apps.schools.signup_views._send_signup_verification_email"
        ) as send:
            resp = self.client.post(
                reverse("resend_signup_verification"),
                {"email": "OWNER@cedar.test"},  # case-insensitive match
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "pending school signup")
        sv.refresh_from_db()
        self.assertNotEqual(sv.token, old_token, "token must rotate so old links die")
        self.assertGreater(sv.expires_at, old_expiry, "expiry must be refreshed")
        self.assertGreater(sv.expires_at, timezone.now(), "new link must be valid")
        send.assert_called_once()

    def test_cooldown_blocks_immediate_second_resend(self):
        sv = self._pending(email="rate@cedar.test", expired=True)
        with mock.patch(
            "apps.schools.signup_views._send_signup_verification_email"
        ) as send:
            self.client.post(
                reverse("resend_signup_verification"), {"email": "rate@cedar.test"}
            )
            sv.refresh_from_db()
            token_after_first = sv.token
            # Immediate second request — must be throttled (no second send, no
            # second rotation) but still return the generic success message.
            resp2 = self.client.post(
                reverse("resend_signup_verification"), {"email": "rate@cedar.test"}
            )
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, "pending school signup")
        sv.refresh_from_db()
        self.assertEqual(sv.token, token_after_first, "throttle must block re-rotation")
        send.assert_called_once()

    def test_active_school_is_not_resent(self):
        # An already-activated (verified) tenant must not get a resend.
        sv = self._pending(email="done@cedar.test")
        sv.verified_at = timezone.now()
        sv.save(update_fields=["verified_at"])
        sv.school.is_active = True
        sv.school.save(update_fields=["is_active"])
        old_token = sv.token
        with mock.patch(
            "apps.schools.signup_views._send_signup_verification_email"
        ) as send:
            resp = self.client.post(
                reverse("resend_signup_verification"), {"email": "done@cedar.test"}
            )
        self.assertEqual(resp.status_code, 200)  # still generic — enumeration-safe
        sv.refresh_from_db()
        self.assertEqual(sv.token, old_token)
        send.assert_not_called()
