"""verify_signup must land a brand-new owner in the guided onboarding wizard —
even when provisioning is ASYNC (broker-backed), so the owner User is NOT
created in-request.

Regression for the 2026-06-08 production dead-end: on Render, ``CELERY_BROKER_URL``
is set, so ``dispatch_provision_school`` queues provisioning on a worker and the
owner User (created inside provisioning) does not exist yet at verify time →
``admin_user`` was None → the new owner was redirected to the login page instead
of the wizard. It "worked in dev" only because the broker-less dev box runs
provisioning synchronously, creating the User in-request. This test pins the
async case by mocking the dispatch to a no-op (worker hasn't run).
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

    def test_async_provisioning_still_redirects_into_onboarding_wizard(self):
        _school, verification = self._pending()
        User = get_user_model()
        self.assertFalse(User.objects.filter(email=verification.email).exists())

        # Simulate ASYNC provisioning: dispatch queues to a worker that has not
        # run yet, so it creates NOTHING in-request (the prod failure mode).
        with mock.patch(
            "apps.schools.tasks.dispatch_provision_school",
            return_value={"queued": True, "fallback": False, "job_id": "job-1"},
        ):
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
        # resolves), NOT an absolute tenant-subdomain URL — the subdomain isn't
        # live until async provisioning activates the school, and redirecting
        # there is what bounced owners to the school-not-found → login wall.
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

    def test_async_provisioning_kicks_background_completion(self):
        school, verification = self._pending()
        with mock.patch(
            "apps.schools.tasks.dispatch_provision_school",
            return_value={"queued": True, "fallback": False, "job_id": "job-1"},
        ):
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
