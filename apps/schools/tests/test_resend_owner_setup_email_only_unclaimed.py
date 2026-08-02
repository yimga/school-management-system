"""`--only-unclaimed` guard on ``resend_owner_setup_email``.

Regression: the Render pre-deploy runs ``seed_tenant_test_accounts --send-owner-email``
(which calls ``resend_owner_setup_email``) on EVERY deploy. Without a guard a set-up
owner received the "your school is ready" email on every release. ``--only-unclaimed``
skips owners who have already claimed a credential (usable password + onboarding),
while an unclaimed owner — and the operator's unflagged force-resend — still receives it.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.schools.models import School, SchoolMembership

User = get_user_model()


class ResendOwnerSetupEmailOnlyUnclaimedTests(TestCase):
    def setUp(self):
        # owner_onboarding "completed" at the school level; combined with a usable
        # password this makes owner_has_claimed_credential() -> True for a claimed owner.
        self.school = School.objects.create(
            name="Gilead Tech Test",
            slug="gilead-tech-test",
            subdomain="gilead-tech-test",
            is_active=True,
            settings={"owner_onboarding": {"completed": True}},
        )

    def _owner(self, email: str, *, claimed: bool):
        user = User.objects.create_user(username=email, email=email)
        if claimed:
            user.set_password("RealPass123!")  # a credential the owner "chose"
        else:
            user.set_unusable_password()  # never claimed (create-if-missing owner)
        user.is_active = True
        user.save()
        SchoolMembership.objects.create(
            user=user, school=self.school, is_school_owner=True, role=User.Role.ADMIN
        )
        return user

    def test_only_unclaimed_skips_claimed_owner(self):
        self._owner("claimed@example.com", claimed=True)
        self._owner("unclaimed@example.com", claimed=False)
        out = StringIO()
        call_command(
            "resend_owner_setup_email",
            "--school", self.school.slug,
            "--only-unclaimed", "--dry-run",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("unclaimed@example.com", text)
        self.assertNotIn("claimed@example.com", text)

    def test_all_claimed_sends_nothing(self):
        self._owner("claimed@example.com", claimed=True)
        out = StringIO()
        call_command(
            "resend_owner_setup_email",
            "--school", self.school.slug,
            "--only-unclaimed", "--dry-run",
            stdout=out,
        )
        # No recipients + benign steady-state message (the "every deploy" fix path).
        self.assertIn("already claimed", out.getvalue())

    def test_forced_resend_without_flag_includes_claimed(self):
        self._owner("claimed@example.com", claimed=True)
        out = StringIO()
        call_command(
            "resend_owner_setup_email",
            "--school", self.school.slug,
            "--dry-run",  # operator force-resend: no --only-unclaimed
            stdout=out,
        )
        self.assertIn("claimed@example.com", out.getvalue())
