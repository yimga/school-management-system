"""End-to-end guards for the public-host signup → onboarding customer journey."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.schools.models import School, SchoolMembership
from apps.schools.provision_email_urls import (
    build_owner_onboarding_url,
    build_public_login_url,
    school_subdomain_redirect_is_safe,
)


def _owner_with_school(*, slug="journey-school", active=False):
    user = get_user_model().objects.create_user(
        username=f"owner-{slug}",
        email=f"owner@{slug}.test",
        role="ADMIN",
    )
    user.set_unusable_password()
    user.save()
    school = School.objects.create(
        name="Journey School",
        slug=slug,
        subdomain=slug,
        is_active=active,
        country_code="US",
    )
    SchoolMembership.objects.create(
        user=user, school=school, role="ADMIN", is_primary=True
    )
    return user, school


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.public_urls",
    RATELIMIT_ENABLE=False,
)
class SignupOnboardingJourneyTests(TestCase):
    def test_welcome_link_targets_public_host_not_subdomain(self):
        user, school = _owner_with_school(slug="newsbell-school-of-arts")
        url = build_owner_onboarding_url(school, user)
        self.assertTrue(url.startswith("https://runmycampus.com/"))
        self.assertIn("/authentication/onboarding/account/", url)
        self.assertNotIn("newsbell-school-of-arts.", url)

    def test_inactive_school_blocks_subdomain_redirect(self):
        _, school = _owner_with_school(active=False)
        self.assertFalse(school_subdomain_redirect_is_safe(school))

    def test_redirect_view_stays_on_public_host_when_school_inactive(self):
        user, school = _owner_with_school(active=False)
        self.client.force_login(
            user, backend="django.contrib.auth.backends.ModelBackend"
        )
        resp = self.client.get(reverse("accounts:redirect"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/authentication/onboarding/done", resp.url)
        self.assertNotIn("journey-school.", resp.url)

    def test_redirect_view_uses_subdomain_when_school_active(self):
        user, school = _owner_with_school(slug="live-school", active=True)
        self.client.force_login(
            user, backend="django.contrib.auth.backends.ModelBackend"
        )
        resp = self.client.get(reverse("accounts:redirect"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("live-school.runmycampus.com", resp.url)

    @mock.patch("apps.accounts.views_owner_onboarding._kick_provisioning_on_done_page")
    def test_onboarding_done_shows_wait_state_when_not_live(self, _kick_mock):
        user, school = _owner_with_school(active=False)
        self.client.force_login(
            user, backend="django.contrib.auth.backends.ModelBackend"
        )
        resp = self.client.get(reverse("accounts:owner_onboarding_done"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"finishing the last setup steps", resp.content.lower())

    def test_public_login_url_is_never_manager(self):
        url = build_public_login_url()
        self.assertIn("runmycampus.com/authentication/login", url)
        self.assertNotIn("manager.", url)

    def test_account_set_password_renders_on_public_host(self):
        user, _school = _owner_with_school()
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        url = reverse(
            "accounts:owner_onboarding_account", kwargs={"uidb64": uid, "token": token}
        )
        client = Client(HTTP_HOST="runmycampus.com")
        r = client.get(url)
        self.assertEqual(r.status_code, 302)
        r2 = client.get(r.url)
        self.assertEqual(r2.status_code, 200)
        self.assertIn(b"Create a password", r2.content)
