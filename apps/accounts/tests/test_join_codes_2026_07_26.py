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
