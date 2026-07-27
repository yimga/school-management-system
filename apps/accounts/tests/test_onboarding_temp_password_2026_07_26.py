"""Admin temp-password provisioning + forced first-login onboarding (Feature 1).

Covers: the provisioning helper (creates a school-linked account with an admin-set
temporary password and forced-onboarding flags), the OnboardingEnforcementMiddleware
(airtight redirect to set-password / profile-setup, inert for set-up users), and the
profile-setup view (marks profile_setup_completed).
"""

from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.middleware import OnboardingEnforcementMiddleware
from apps.accounts.tenant_user_provisioning import (
    ProvisioningError,
    provision_tenant_user_with_temp_password,
    provisionable_role_choices,
)
from apps.accounts.views_onboarding import onboarding_profile
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class ProvisionTempPasswordTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )

    def test_provisions_user_with_forced_onboarding(self):
        user, created = provision_tenant_user_with_temp_password(
            school=self.school, email="t1@ex.com", role="TEACHER", temp_password="Temp1234"
        )
        self.assertTrue(created)
        self.assertTrue(user.requires_password_change)
        self.assertFalse(user.profile_setup_completed)
        self.assertTrue(user.needs_onboarding())
        # The temp password authenticates.
        self.assertIsNotNone(authenticate(username="t1@ex.com", password="Temp1234"))
        # Linked to the school with the requested role.
        self.assertTrue(
            SchoolMembership.objects.filter(
                user=user, school=self.school, role="TEACHER"
            ).exists()
        )

    def test_parent_role_is_provisionable(self):
        user, _ = provision_tenant_user_with_temp_password(
            school=self.school, email="p1@ex.com", role="PARENT", temp_password="Temp1234"
        )
        self.assertEqual(user.role, "PARENT")
        self.assertTrue(user.needs_onboarding())

    def test_rejects_short_password(self):
        with self.assertRaises(ProvisioningError):
            provision_tenant_user_with_temp_password(
                school=self.school, email="x@ex.com", role="TEACHER", temp_password="short"
            )

    def test_rejects_non_provisionable_role(self):
        with self.assertRaises(ProvisioningError):
            provision_tenant_user_with_temp_password(
                school=self.school, email="s@ex.com", role="STUDENT", temp_password="Temp1234"
            )

    def test_rejects_existing_active_account(self):
        User.objects.create_user(
            username="dup@ex.com", email="dup@ex.com", password="Existing123!"
        )
        with self.assertRaises(ProvisioningError):
            provision_tenant_user_with_temp_password(
                school=self.school, email="dup@ex.com", role="TEACHER", temp_password="Temp1234"
            )

    def test_activates_unactivated_account_without_clobber_error(self):
        # An account with an UNUSABLE password (e.g. invited-but-not-set) may be provisioned.
        u = User.objects.create_user(username="pending@ex.com", email="pending@ex.com")
        u.set_unusable_password()
        u.save()
        user, created = provision_tenant_user_with_temp_password(
            school=self.school, email="pending@ex.com", role="SECRETARY", temp_password="Temp1234"
        )
        self.assertFalse(created)
        self.assertTrue(user.requires_password_change)
        self.assertIsNotNone(authenticate(username="pending@ex.com", password="Temp1234"))

    def test_provisionable_roles_exclude_deny_set(self):
        vals = {v for v, _ in provisionable_role_choices()}
        self.assertIn("TEACHER", vals)
        self.assertIn("PARENT", vals)
        self.assertNotIn("STUDENT", vals)
        self.assertNotIn("SUPERADMIN", vals)


class OnboardingMiddlewareTests(TestCase):
    def _mw(self):
        return OnboardingEnforcementMiddleware(lambda req: HttpResponse("PASSTHROUGH"))

    def _req(self, path="/zzz-nonexistent-page/"):
        return RequestFactory().get(path, HTTP_ACCEPT="text/html")

    def test_passes_setup_user(self):
        req = self._req()
        req.user = User(
            username="ok", requires_password_change=False, profile_setup_completed=True
        )
        self.assertEqual(self._mw()(req).content, b"PASSTHROUGH")

    def test_ignores_anonymous(self):
        req = self._req()
        req.user = AnonymousUser()
        self.assertEqual(self._mw()(req).content, b"PASSTHROUGH")

    def test_redirects_to_password_change(self):
        req = self._req()
        req.user = User(
            username="need", requires_password_change=True, profile_setup_completed=False
        )
        resp = self._mw()(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:password_change"), resp["Location"])

    def test_redirects_to_profile_when_only_profile_incomplete(self):
        req = self._req()
        req.user = User(
            username="prof", requires_password_change=False, profile_setup_completed=False
        )
        resp = self._mw()(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:onboarding_profile"), resp["Location"])

    def test_allows_the_wizard_paths(self):
        req = RequestFactory().get(
            reverse("accounts:password_change"), HTTP_ACCEPT="text/html"
        )
        req.user = User(
            username="need2", requires_password_change=True, profile_setup_completed=False
        )
        self.assertEqual(self._mw()(req).content, b"PASSTHROUGH")

    def test_xhr_passes_through(self):
        req = RequestFactory().get(
            "/zzz/", HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="text/html"
        )
        req.user = User(
            username="xhr", requires_password_change=True, profile_setup_completed=False
        )
        self.assertEqual(self._mw()(req).content, b"PASSTHROUGH")

    def test_superuser_never_trapped(self):
        req = self._req()
        req.user = User(
            username="op",
            is_superuser=True,
            requires_password_change=True,
            profile_setup_completed=False,
        )
        self.assertEqual(self._mw()(req).content, b"PASSTHROUGH")


class OnboardingProfileViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )
        self.user, _ = provision_tenant_user_with_temp_password(
            school=self.school, email="v@ex.com", role="TEACHER", temp_password="Temp1234"
        )

    def _req(self, method, data=None):
        rf = RequestFactory()
        req = getattr(rf, method)(reverse("accounts:onboarding_profile"), data or {})
        req.user = self.user
        req.session = SessionStore()
        req.session.create()
        req._messages = FallbackStorage(req)
        return req

    def test_redirects_to_password_change_when_pw_still_pending(self):
        resp = onboarding_profile(self._req("get"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:password_change"), resp["Location"])

    def test_completes_profile_after_password_done(self):
        # Simulate the set-password step already cleared.
        self.user.requires_password_change = False
        self.user.save(update_fields=["requires_password_change"])
        resp = onboarding_profile(
            self._req("post", {"first_name": "Ada", "last_name": "Lovelace"})
        )
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.profile_setup_completed)
        self.assertEqual(self.user.first_name, "Ada")
        self.assertFalse(self.user.needs_onboarding())

    def test_name_required(self):
        self.user.requires_password_change = False
        self.user.save(update_fields=["requires_password_change"])
        resp = onboarding_profile(self._req("post", {"first_name": "", "last_name": ""}))
        self.assertEqual(resp.status_code, 200)  # re-render with errors
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_setup_completed)
