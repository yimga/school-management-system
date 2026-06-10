"""verify_signup must create the owner up-front and land a brand-new owner in
the guided onboarding wizard, while provisioning runs in the BACKGROUND so the
owner watches a live progress bar (and verify never blocks/times out).

Regression for the 2026-06-08 production dead-end: the owner User (created inside
provisioning) didn't exist at verify time on broker-backed deploys → ``admin_user``
was None → the owner was redirected to the login page instead of the wizard.
verify now creates the owner up-front itself, then kicks provisioning to run in
the background (a daemon-thread completion for queued dispatch; sync fallback when
no broker) and redirects into the onboarding launchpad. Reliability is guaranteed
by the progress poll endpoint's watchdog (auto-kick of a stalled job), not by
blocking the verify request. These tests pin: owner created up-front, redirect
into the wizard (never the login wall), and a background completion kicked.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.schools.models import School, SignupVerification


@override_settings(RATELIMIT_ENABLE=False)
class VerifySignupOnboardingTests(TestCase):
    def setUp(self):
        cache.clear()

    def _pending(self, email="newowner@cedar.test"):
        school = School.objects.create(
            name="Cedar School",
            slug="cedar-vs",
            subdomain="cedar-vs",
            is_active=False,
            country_code="US",
        )
        verification = SignupVerification.objects.create(
            school=school,
            email=email,
            token=uuid.uuid4(),
            expires_at=timezone.now() + timedelta(days=2),
        )
        return school, verification

    def test_verify_redirects_into_onboarding_wizard(self):
        _school, verification = self._pending()
        User = get_user_model()
        self.assertFalse(User.objects.filter(email=verification.email).exists())

        # Provisioning is kicked in the background (no-op here); verify must STILL
        # create the owner up-front and redirect into the wizard (owner row is
        # created by verify itself, independent of the background job).
        with mock.patch(
            "apps.schools.tasks.kick_complete_provisioning_background"
        ):
            resp = self.client.get(
                reverse("verify_signup") + f"?token={verification.token}"
            )

        # verify_signup must create the owner row up-front itself...
        owner = User.objects.filter(email=verification.email).first()
        self.assertIsNotNone(owner, "owner account was not created at verify time")

        # ...and redirect INTO the onboarding wizard, never the login wall.
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/authentication/onboarding/account/", resp.url)
        self.assertNotIn("/authentication/login", resp.url)
        # The redirect MUST be relative (stay on the public host that always
        # resolves), NOT an absolute tenant-subdomain URL.
        self.assertTrue(resp.url.startswith("/authentication/onboarding/account/"))
        self.assertFalse(resp.url.lower().startswith("http"))

    def test_owner_creation_is_idempotent_when_user_already_exists(self):
        # A retry / double-click must not create a second account or crash.
        _school, verification = self._pending(email="dupe@cedar.test")
        from apps.schools.tasks import ensure_admin_user_for_school

        u1, created1 = ensure_admin_user_for_school(_school, verification.email)
        u2, created2 = ensure_admin_user_for_school(_school, verification.email)
        self.assertEqual(u1.pk, u2.pk)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(
            get_user_model().objects.filter(email=verification.email).count(), 1
        )

    def test_verify_kicks_background_completion(self):
        school, verification = self._pending()
        # verify must kick a background completion (fast, non-blocking) so
        # provisioning runs while the owner watches the live progress bar —
        # without blocking the verify request.
        with mock.patch(
            "apps.schools.tasks.kick_complete_provisioning_background"
        ) as kick:
            self.client.get(
                reverse("verify_signup") + f"?token={verification.token}"
            )
        kick.assert_called_once_with(
            str(school.id), contact_email=verification.email
        )


class OnboardingGateAllowlistTests(TestCase):
    """The onboarding wizard must survive the two gates that otherwise eject a
    brand-new, passwordless owner: the strict conversion lock and the MFA-setup
    requirement. Without these the wizard redirects to /activation/first-action/
    → /authentication/mfa/setup/ → the manager login wall."""

    def test_onboarding_allowlisted_in_strict_conversion_lock(self):
        from apps.schools.conversion_lock_paths import (
            CONVERSION_LOCK_AUTH_PREFIXES_STRICT,
        )

        self.assertIn(
            "/authentication/onboarding/", CONVERSION_LOCK_AUTH_PREFIXES_STRICT
        )

    def test_onboarding_bypasses_mfa_setup_gate(self):
        from apps.accounts.middleware import RequireMFAMiddleware

        self.assertIn(
            "/authentication/onboarding/", RequireMFAMiddleware.BYPASS_PREFIXES
        )


class OnboardingHostRoutingTests(TestCase):
    """The wizard must be served on the PUBLIC site for an anonymous, token-authed
    owner — NOT 302'd to the manager host, where ManagerHostControlPlaneRequired
    forces an operator login (the exact reported dead-end:
    manager.../login/?next=/mfa/setup/?next=/activation/first-action/)."""

    def test_onboarding_is_not_manager_only(self):
        # Base host serves it directly (not redirected to manager.<base>).
        from apps.schools.middleware import _is_manager_only_path

        self.assertFalse(
            _is_manager_only_path("/authentication/onboarding/account/abc/def/")
        )
        self.assertFalse(_is_manager_only_path("/authentication/onboarding/school/"))
        # Sanity: other /authentication/ paths stay manager-only (no over-reach).
        self.assertTrue(_is_manager_only_path("/authentication/profile/"))

    def test_command_bar_actions_resolves_on_public_host(self):
        from django.urls import reverse

        with override_settings(ROOT_URLCONF="config.public_urls"):
            self.assertEqual(
                reverse("command_bar_actions"), "/api/command-bar/actions/"
            )

    @override_settings(
        MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
        ROOT_URLCONF="config.manager_urls",
        RMC_PUBLIC_SITE_URL="https://runmycampus.com",
        ALLOWED_HOSTS=["*", "manager.runmycampus.com"],
    )
    def test_manager_verify_signup_redirects_to_public_host(self):
        resp = self.client.get(
            "/verify-signup/?token=00000000-0000-0000-0000-000000000001",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("runmycampus.com", resp.url)
        self.assertNotIn("manager.", resp.url)

    def test_onboarding_is_anonymous_safe_on_manager_host(self):
        # Defense-in-depth: if it ever lands on manager, served anonymously
        # (token-authed) instead of bounced to the control-plane login.
        from apps.schools.middleware import (
            MANAGER_HOST_PUBLIC_ACCESS_PREFIXES,
            _path_allowed_for_reserved_host,
        )

        self.assertTrue(
            _path_allowed_for_reserved_host(
                "/authentication/onboarding/account/abc/def/",
                allowed_prefixes=MANAGER_HOST_PUBLIC_ACCESS_PREFIXES,
            )
        )

    def test_password_reset_allowed_on_manager_host(self):
        from apps.schools.middleware import (
            MANAGER_AUTH_ALLOWED_PREFIXES,
            _path_allowed_for_reserved_host,
        )

        self.assertTrue(
            _path_allowed_for_reserved_host(
                "/authentication/password_reset/",
                allowed_prefixes=MANAGER_AUTH_ALLOWED_PREFIXES,
            )
        )
        self.assertTrue(
            _path_allowed_for_reserved_host(
                "/authentication/reset/abc/def/",
                allowed_prefixes=MANAGER_AUTH_ALLOWED_PREFIXES,
            )
        )

    def test_password_reset_allowed_under_conversion_lock(self):
        from apps.schools.conversion_lock_paths import (
            CONVERSION_LOCK_AUTH_PREFIXES_STRICT,
        )

        self.assertIn(
            "/authentication/password_reset/", CONVERSION_LOCK_AUTH_PREFIXES_STRICT
        )
        self.assertIn("/authentication/reset/", CONVERSION_LOCK_AUTH_PREFIXES_STRICT)
