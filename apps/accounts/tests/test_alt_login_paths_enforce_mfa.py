"""Non-password sign-in paths must issue the MFA challenge too.

``resolve_post_login_mfa_redirect`` is the only code in the repo that issues an
MFA challenge, and it was called from exactly one place: the password
``login_view``. Every other ``login()`` call site skipped it, under the comment
"MFA (if enrolled) is still enforced by RequireMFAMiddleware after login".

That comment was false. ``RequireMFAMiddleware`` asks ``resolve_mfa_enforcement``,
whose first statement is ``if not must_have_mfa or has_device: return "none"``
(apps/accounts/mfa_defaults.py). The middleware only ever walls users who have NO
device -- it never inspects ``request.session["mfa_verified"]``. So a user who IS
enrolled sails straight through it.

Concretely: an ADMIN with a confirmed TOTP device POSTs their own address to
/authentication/magic-link/, clicks the emailed link, and gets a fully privileged
session with no TOTP code ever requested. Second factor reduced to possession of
the mailbox.

The join-code and claim-invite paths log in accounts that were just created, so
they never carry a device -- the middleware does cover those today. They are
wired to the same resolver anyway, so enrollment policy is decided in one place
rather than by which view happened to run.
"""

from __future__ import annotations

import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import LoginMagicLink, User
from apps.schools.models import School, SchoolMembership


class MagicLinkHonoursMfaTests(TestCase):
    def setUp(self) -> None:
        tag = uuid.uuid4().hex[:10]
        self.school = School.objects.create(
            name="Magic High",
            slug=f"mag-{tag}",
            subdomain=f"mag-{tag}",
            is_active=True,
        )
        self.host = f"{self.school.subdomain}.runmycampus.com"

    def _member(self, role):
        tag = uuid.uuid4().hex[:8]
        user = User.objects.create_user(
            username=f"{role.lower()}-{tag}",
            email=f"{role.lower()}-{tag}@example.com",
            password="pass12345678",
            role=role,
        )
        SchoolMembership.objects.create(user=user, school=self.school, role=role)
        return user

    def _link(self, user):
        return LoginMagicLink.objects.create(
            user=user,
            school=self.school,
            expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )

    def _click(self, link):
        return self.client.get(
            reverse("accounts:magic_link_login", kwargs={"token": str(link.token)}),
            HTTP_HOST=self.host,
        )

    def test_enrolled_user_is_challenged_instead_of_landing_on_the_dashboard(self):
        user = self._member(User.Role.ADMIN)
        TOTPDevice.objects.create(user=user, name="totp", confirmed=True)
        link = self._link(user)

        response = self._click(link)

        self.assertEqual(response.status_code, 302)
        # Guard against a vacuous pass: an invalid or expired token ALSO redirects
        # (to magic_link_request) without logging anyone in, so "not the
        # dashboard" would pass against a broken fixture. Prove the link was
        # actually consumed and the session really belongs to this user first.
        link.refresh_from_db()
        self.assertIsNotNone(link.used_at)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        self.assertEqual(response["Location"], reverse("accounts:mfa_verify"))
        self.assertFalse(self.client.session.get("mfa_verified"))

    def test_an_unenrolled_parent_still_signs_in(self):
        """Guard: the fix must not wall the un-enrolled.

        Enrollment policy for a user with no device belongs to the tenant's
        soft-launch mode, not to this path. A PARENT is in no required-role list,
        so the resolver must return None and the link must land where it always
        did.
        """
        user = self._member(User.Role.PARENT)
        link = self._link(user)

        response = self._click(link)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        self.assertNotEqual(response["Location"], reverse("accounts:mfa_verify"))

    def test_a_remembered_verification_is_not_re_challenged(self):
        """An enrolled user whose session already passed MFA is not bounced.

        ``resolve_post_login_mfa_redirect`` returns None when
        ``session["mfa_verified"]`` is set; this pins that the magic-link path
        goes through the resolver rather than hard-coding a redirect.
        """
        user = self._member(User.Role.ADMIN)
        TOTPDevice.objects.create(user=user, name="totp", confirmed=True)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()
        link = self._link(user)

        response = self._click(link)

        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        self.assertNotEqual(response["Location"], reverse("accounts:mfa_verify"))
