"""v4.00.95 Wave E5 — short-link helper tests (pure-fn paths)."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.assist_dock.short_links import (
    SHORT_LINK_MAX_TTL_HOURS,
    SHORT_LINK_MAX_URL_LEN,
    is_safe_target,
    make_token,
    mint_short_link,
)


class TokenTests(SimpleTestCase):
    def test_token_is_urlsafe_and_bounded(self):
        token = make_token()
        self.assertGreater(len(token), 8)
        self.assertLessEqual(len(token), 32)
        # urlsafe_b64 chars only.

        self.assertRegex(token, r"^[A-Za-z0-9_-]+$")

    def test_tokens_are_unique_across_calls(self):
        tokens = {make_token() for _ in range(50)}
        self.assertEqual(len(tokens), 50)


class SafeTargetTests(SimpleTestCase):
    def test_empty_rejected(self):
        self.assertFalse(is_safe_target(""))

    def test_protocol_relative_rejected(self):
        self.assertFalse(is_safe_target("//evil.example/foo"))

    def test_site_relative_allowed(self):
        self.assertTrue(is_safe_target("/portal/dashboard/"))

    def test_javascript_url_rejected(self):
        self.assertFalse(is_safe_target("javascript:alert(1)"))

    def test_absolute_url_allowed_for_listed_host(self):
        with self.settings(ALLOWED_HOSTS=["runmycampus.local", ".runmycampus.test"]):
            self.assertTrue(is_safe_target("https://runmycampus.local/path/"))
            self.assertTrue(is_safe_target("https://tenant.runmycampus.test/path/"))

    def test_absolute_url_rejected_for_unlisted_host(self):
        with self.settings(ALLOWED_HOSTS=["runmycampus.local"]):
            self.assertFalse(is_safe_target("https://evil.example/path/"))

    def test_star_host_allows_all(self):
        with self.settings(ALLOWED_HOSTS=["*"]):
            self.assertTrue(is_safe_target("https://anything.example/x/"))


class MintShortLinkTests(SimpleTestCase):
    def test_anonymous_rejected(self):
        link, err = mint_short_link(target_url="/x/", created_by=None)
        self.assertIsNone(link)
        self.assertEqual(err, "anonymous")

    def test_empty_target_rejected(self):
        user = mock.Mock(pk=1)
        link, err = mint_short_link(target_url="", created_by=user)
        self.assertIsNone(link)
        self.assertEqual(err, "target_required")

    def test_oversize_target_rejected(self):
        user = mock.Mock(pk=1)
        big = "/" + "x" * (SHORT_LINK_MAX_URL_LEN + 1)
        link, err = mint_short_link(target_url=big, created_by=user)
        self.assertIsNone(link)
        self.assertEqual(err, "target_too_long")

    def test_unsafe_target_rejected(self):
        user = mock.Mock(pk=1)
        link, err = mint_short_link(
            target_url="https://evil.example/", created_by=user
        )
        self.assertIsNone(link)
        self.assertEqual(err, "target_not_allowed")

    def test_ttl_clamped(self):
        user = mock.Mock(pk=1)
        fake_link = mock.Mock(token="abc", expires_at=None)
        with mock.patch(
            "apps.assist_dock.models.AssistDockShortLink.objects.create",
            return_value=fake_link,
        ) as create:
            link, err = mint_short_link(
                target_url="/x/", created_by=user, ttl_hours=99999
            )
            self.assertIsNotNone(link)
            self.assertEqual(err, "")
            call_kwargs = create.call_args.kwargs
            from django.utils import timezone
            from datetime import timedelta

            max_window = timezone.now() + timedelta(hours=SHORT_LINK_MAX_TTL_HOURS + 1)
            self.assertLessEqual(call_kwargs["expires_at"], max_window)
