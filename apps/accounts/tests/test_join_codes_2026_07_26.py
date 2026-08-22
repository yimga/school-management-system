"""Self-service school join codes (Feature 2).

Covers generation (role validation, uniqueness) and redemption (creates a
school-linked account, increments uses, enforces domain allowlist / caps / expiry /
deactivation, and blocks an existing active account).
"""

from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.join_codes import (
    JoinCodeError,
    generate_join_code,
    redeem_join_code,
    resolve_join_code,
)
from apps.accounts.models import SchoolJoinCode
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class JoinCodeGenerationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )

    def test_generate_creates_usable_code(self):
        jc = generate_join_code(school=self.school, role="PARENT")
        self.assertTrue(jc.is_usable)
        self.assertEqual(len(jc.code), 8)
        self.assertEqual(jc.role, "PARENT")

    def test_generate_rejects_non_provisionable_role(self):
        with self.assertRaises(JoinCodeError):
            generate_join_code(school=self.school, role="STUDENT")

    def test_resolve_scoped_to_school(self):
        jc = generate_join_code(school=self.school, role="TEACHER")
        self.assertEqual(resolve_join_code(jc.code, school=self.school), jc)
        other = School.objects.create(
            name="Other", slug="other", subdomain="other", is_active=True
        )
        self.assertIsNone(resolve_join_code(jc.code, school=other))


class JoinCodeRedemptionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )

    def test_redeem_creates_linked_account(self):
        jc = generate_join_code(school=self.school, role="PARENT")
        user = redeem_join_code(
            code=jc.code, email="mum@ex.com", password="ChosenPw123",
            first_name="Grace", last_name="Hopper", school=self.school,
        )
        self.assertEqual(user.role, "PARENT")
        self.assertTrue(user.profile_setup_completed)
        self.assertFalse(user.requires_password_change)
        self.assertFalse(user.needs_onboarding())
        self.assertIsNotNone(authenticate(username="mum@ex.com", password="ChosenPw123"))
        self.assertTrue(
            SchoolMembership.objects.filter(user=user, school=self.school, role="PARENT").exists()
        )
        jc.refresh_from_db()
        self.assertEqual(jc.uses_count, 1)

    def test_domain_allowlist_enforced(self):
        jc = generate_join_code(
            school=self.school, role="TEACHER", domain_allowlist="school.edu, staff.school.edu"
        )
        with self.assertRaises(JoinCodeError):
            redeem_join_code(
                code=jc.code, email="t@gmail.com", password="ChosenPw123", school=self.school
            )
        user = redeem_join_code(
            code=jc.code, email="t@school.edu", password="ChosenPw123", school=self.school
        )
        self.assertEqual(user.email, "t@school.edu")

    def test_max_uses_exhaustion(self):
        jc = generate_join_code(school=self.school, role="PARENT", max_uses=1)
        redeem_join_code(code=jc.code, email="a@ex.com", password="ChosenPw123", school=self.school)
        with self.assertRaises(JoinCodeError):
            redeem_join_code(code=jc.code, email="b@ex.com", password="ChosenPw123", school=self.school)

    def test_expired_code_rejected(self):
        jc = generate_join_code(school=self.school, role="PARENT")
        SchoolJoinCode.objects.filter(pk=jc.pk).update(
            expires_at=timezone.now() - timezone.timedelta(days=1)
        )
        with self.assertRaises(JoinCodeError):
            redeem_join_code(code=jc.code, email="c@ex.com", password="ChosenPw123", school=self.school)

    def test_deactivated_code_rejected(self):
        jc = generate_join_code(school=self.school, role="PARENT")
        SchoolJoinCode.objects.filter(pk=jc.pk).update(is_active=False)
        with self.assertRaises(JoinCodeError):
            redeem_join_code(code=jc.code, email="d@ex.com", password="ChosenPw123", school=self.school)

    def test_existing_active_account_blocked(self):
        User.objects.create_user(username="dup@ex.com", email="dup@ex.com", password="Existing123!")
        jc = generate_join_code(school=self.school, role="PARENT")
        with self.assertRaises(JoinCodeError):
            redeem_join_code(code=jc.code, email="dup@ex.com", password="ChosenPw123", school=self.school)

    def test_short_password_rejected(self):
        jc = generate_join_code(school=self.school, role="PARENT")
        with self.assertRaises(JoinCodeError):
            redeem_join_code(code=jc.code, email="e@ex.com", password="short", school=self.school)

    def test_wrong_code_rejected(self):
        with self.assertRaises(JoinCodeError):
            redeem_join_code(code="NOTACODE", email="f@ex.com", password="ChosenPw123", school=self.school)


class JoinCodeNeverAdoptsExistingAccountTests(TestCase):
    """A join code must never take over an account that already exists.

    Redemption used to block an existing account only when
    ``has_usable_password()`` was True. But ``set_unusable_password()`` is how
    this codebase provisions every federated and imported identity -- OIDC, SAML,
    SCIM, roster sync, the migration landers, and self-serve provisioned owners --
    so every one of those was adoptable by anyone holding the code. Join codes are
    public and deliberately shareable (there is a poster view), and
    ``views_join.join_school`` calls ``login()`` on the result, so the caller
    landed signed in AS the victim.

    ``test_existing_active_account_blocked`` above covers only the usable-password
    case, which is why this went unnoticed.
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )

    def _federated_user(self, email="teacher@school.edu"):
        """A user shaped exactly like the OIDC/SAML/SCIM provisioning paths."""
        user = User.objects.create(username=email, email=email, role="TEACHER")
        user.set_unusable_password()
        user.save()
        return user

    def test_unusable_password_account_is_not_adopted(self):
        victim = self._federated_user()
        jc = generate_join_code(school=self.school, role="TEACHER")
        with self.assertRaises(JoinCodeError):
            redeem_join_code(
                code=jc.code,
                email="teacher@school.edu",
                password="AttackerChosen123",
                school=self.school,
            )
        victim.refresh_from_db()
        # The attacker's password must NOT have been written to the victim's row.
        self.assertFalse(victim.has_usable_password())
        self.assertIsNone(
            authenticate(username="teacher@school.edu", password="AttackerChosen123")
        )

    def test_refused_redemption_creates_no_membership_and_burns_no_use(self):
        self._federated_user("staff@school.edu")
        jc = generate_join_code(school=self.school, role="TEACHER")
        with self.assertRaises(JoinCodeError):
            redeem_join_code(
                code=jc.code,
                email="staff@school.edu",
                password="AttackerChosen123",
                school=self.school,
            )
        self.assertFalse(
            SchoolMembership.objects.filter(
                user__email="staff@school.edu", school=self.school
            ).exists()
        )
        jc.refresh_from_db()
        self.assertEqual(jc.uses_count, 0)

    def test_case_insensitive_email_cannot_slip_past(self):
        self._federated_user("mixed@school.edu")
        jc = generate_join_code(school=self.school, role="TEACHER")
        with self.assertRaises(JoinCodeError):
            redeem_join_code(
                code=jc.code,
                email="MiXeD@School.EDU",
                password="AttackerChosen123",
                school=self.school,
            )

    def test_a_genuinely_new_email_still_works(self):
        # The fix must not break the feature it guards.
        jc = generate_join_code(school=self.school, role="TEACHER")
        user = redeem_join_code(
            code=jc.code,
            email="brandnew@school.edu",
            password="ChosenPw123",
            school=self.school,
        )
        self.assertEqual(user.email, "brandnew@school.edu")
        self.assertTrue(user.has_usable_password())
        self.assertTrue(
            SchoolMembership.objects.filter(user=user, school=self.school).exists()
        )
