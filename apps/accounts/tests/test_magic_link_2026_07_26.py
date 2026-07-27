"""Passwordless magic-link sign-in (Feature 3).

Covers request (creates a link for an existing active user, enumeration-safe for
unknown emails, rate-limited) and consume (single-use, expiry, school scoping).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.magic_link import (
    _MAX_PER_WINDOW,
    consume_magic_link,
    request_magic_link,
)
from apps.accounts.models import LoginMagicLink
from apps.schools.models import School

User = get_user_model()


class MagicLinkRequestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="jo@ex.com", email="jo@ex.com", password="Existing123!", is_active=True
        )

    def test_creates_link_for_existing_user(self):
        request_magic_link("jo@ex.com")
        self.assertTrue(LoginMagicLink.objects.filter(user=self.user).exists())

    def test_no_link_for_unknown_email(self):
        request_magic_link("nobody@ex.com")
        self.assertEqual(LoginMagicLink.objects.count(), 0)

    def test_no_link_for_blank_email(self):
        self.assertFalse(request_magic_link(""))
        self.assertEqual(LoginMagicLink.objects.count(), 0)

    def test_rate_limited(self):
        now = timezone.now()
        for _ in range(_MAX_PER_WINDOW):
            LoginMagicLink.objects.create(
                user=self.user, expires_at=now + timezone.timedelta(minutes=15)
            )
        request_magic_link("jo@ex.com")  # over the window cap
        self.assertEqual(LoginMagicLink.objects.filter(user=self.user).count(), _MAX_PER_WINDOW)


class MagicLinkConsumeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ka@ex.com", email="ka@ex.com", password="Existing123!", is_active=True
        )

    def _link(self, **kw):
        defaults = {
            "user": self.user,
            "expires_at": timezone.now() + timezone.timedelta(minutes=15),
        }
        defaults.update(kw)
        return LoginMagicLink.objects.create(**defaults)

    def test_consume_valid_returns_user_and_marks_used(self):
        link = self._link()
        got = consume_magic_link(link.token)
        self.assertEqual(got, self.user)
        link.refresh_from_db()
        self.assertIsNotNone(link.used_at)

    def test_single_use(self):
        link = self._link()
        self.assertEqual(consume_magic_link(link.token), self.user)
        self.assertIsNone(consume_magic_link(link.token))  # second time fails

    def test_expired_rejected(self):
        link = self._link(expires_at=timezone.now() - timezone.timedelta(minutes=1))
        self.assertIsNone(consume_magic_link(link.token))

    def test_unknown_token_rejected(self):
        import uuid

        self.assertIsNone(consume_magic_link(uuid.uuid4()))

    def test_school_scoping(self):
        school = School.objects.create(
            name="Gilead", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )
        other = School.objects.create(
            name="Other", slug="other", subdomain="other", is_active=True
        )
        link = self._link(school=school)
        # Wrong school → rejected; correct school → ok.
        self.assertIsNone(consume_magic_link(link.token, school=other))
        self.assertEqual(consume_magic_link(link.token, school=school), self.user)
