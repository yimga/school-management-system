"""The post-provisioning welcome email must route owners who have NOT yet
established their OWN credential to ACCOUNT SETUP, not to a sign-in screen.

Root cause fixed here: ``build_signup_completed_payload`` gated ``account_ready``
on ``admin_user.has_usable_password()``, which is ``True`` for an operator/sales-
provisioned owner whose password was set by staff (``create_school``) and who
therefore knows no credential. That owner received the "Sign in ... use the
email and password you created during setup" branch and was stranded at a login
screen. The gate now means "the owner personally claimed a credential" (ran the
token-gated onboarding step, stamped in ``School.settings["owner_onboarding"]``).
When unclaimed, ``activation_url`` is emitted so the email renders its
"Set your password & open your portal" branch instead.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.schools.models import School
from apps.schools.signup_completion_notifications import (
    build_signup_completed_payload,
)


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com", DEBUG=False)
class WelcomeEmailAccountSetupRoutingTests(TestCase):
    def _school(self, **settings_blob):
        school = School.objects.create(
            name="Routing Test School",
            slug="routing-test-school",
            subdomain="routing-test-school",
        )
        if settings_blob:
            school.settings = settings_blob
            school.save(update_fields=["settings"])
        return school

    def _owner(self, *, usable_password):
        user = get_user_model().objects.create_user(
            username="routing_owner",
            email="owner@routingtest.test",
        )
        if usable_password:
            user.set_password("OwnerChosen!234")
        else:
            user.set_unusable_password()
        user.save()
        return user

    def _payload(self, school, owner):
        return build_signup_completed_payload(school, owner.email, admin_user=owner)

    def test_operator_provisioned_owner_routes_to_account_setup(self):
        """THE bug: a staff-set password (no self-claim) must NOT be treated as
        ready-to-sign-in. Route to the account-setup link instead."""
        school = self._school()  # no owner_onboarding state
        owner = self._owner(usable_password=True)  # password set by staff
        payload = self._payload(school, owner)
        self.assertFalse(
            payload["account_ready"],
            "operator-set password was mistaken for an owner-claimed credential",
        )
        self.assertTrue(
            payload["activation_url"],
            "no activation link emitted for an owner who must still set up",
        )
        self.assertIn(
            "/authentication/onboarding/account/", payload["activation_url"]
        )

    def test_owner_with_no_password_routes_to_account_setup(self):
        school = self._school()
        owner = self._owner(usable_password=False)
        payload = self._payload(school, owner)
        self.assertFalse(payload["account_ready"])
        self.assertTrue(payload["activation_url"])

    def test_self_claimed_owner_routes_to_sign_in(self):
        """Owner who finished onboarding (set their OWN password) -> sign-in."""
        school = self._school(owner_onboarding={"completed": True, "step": "done"})
        owner = self._owner(usable_password=True)
        payload = self._payload(school, owner)
        self.assertTrue(payload["account_ready"])
        self.assertEqual(payload["activation_url"], "")

    def test_owner_who_set_password_at_step_one_is_claimed(self):
        """Step 1 (owner sets their OWN password) stamps step='school' -> counts
        as claimed even before the wizard's final launchpad."""
        school = self._school(owner_onboarding={"step": "school"})
        owner = self._owner(usable_password=True)
        payload = self._payload(school, owner)
        self.assertTrue(payload["account_ready"])
        self.assertEqual(payload["activation_url"], "")

    def test_half_written_state_without_password_is_not_claimed(self):
        """A step marker alone must not green-light an owner with no credential."""
        school = self._school(owner_onboarding={"step": "school"})
        owner = self._owner(usable_password=False)
        payload = self._payload(school, owner)
        self.assertFalse(payload["account_ready"])
        self.assertTrue(payload["activation_url"])
