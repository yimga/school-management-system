"""Operator-team admin-assisted password reset (email-independent recovery).

The operator-side twin of the tenant credential reset: a TEAM_MANAGE operator issues
a colleague a one-time temporary password shown on-screen (no email required — the
recovery path for low-connectivity users whose "forgot my password" email never
arrives). Covers: the temp password + forced change, reactivation of an inactive
operator, and the canonical-platform-admin peer-reset protection.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.operator_identity import CANONICAL_PLATFORM_ADMIN_USERNAME
from apps.test_utils.http_clients import login_manager_client

_MANAGER_HOST = "manager.runmycampus.com"
_TEMP = "KnownTemp-9x7QkZ2"  # deterministic via patched generate_temp_password


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MANAGER_HOST],
    SECURE_SSL_REDIRECT=False,
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.manager_urls",
    SESSION_PINNING_ENABLED=False,
)
class OperatorTeamResetPasswordTests(TransactionTestCase):
    def setUp(self):
        self.password = "actorpass123"
        self.actor = User.objects.create_user(
            username=f"op_actor_{uuid.uuid4().hex[:8]}",
            password=self.password,
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(self.actor, password=self.password)
        cache.clear()
        self.host = _MANAGER_HOST

    def _url(self, uid):
        return reverse("super:operator_team_reset_password", args=[uid])

    def _target(self, *, active=True):
        return User.objects.create_user(
            username=f"op_target_{uuid.uuid4().hex[:8]}",
            password="oldpass123",
            is_staff=True,
            is_active=active,
        )

    @patch("apps.accounts.credential_reset.generate_temp_password", return_value=_TEMP)
    def test_reset_issues_temp_password_and_forces_change(self, _mock):
        target = self._target()
        resp = self.client.post(self._url(target.pk), HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 302, msg=resp.get("Location", ""))
        target.refresh_from_db()
        self.assertTrue(target.requires_password_change)
        # The old password is dead; the handed-over temp password authenticates.
        self.assertIsNone(authenticate(username=target.username, password="oldpass123"))
        resolved = authenticate(username=target.username, password=_TEMP)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, target.pk)

    @patch("apps.accounts.credential_reset.generate_temp_password", return_value=_TEMP)
    def test_reset_reactivates_inactive_operator(self, _mock):
        target = self._target(active=False)
        # Before: an inactive account can never authenticate, temp password or not.
        self.assertIsNone(authenticate(username=target.username, password="oldpass123"))
        self.client.post(self._url(target.pk), HTTP_HOST=self.host)
        target.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertIsNotNone(authenticate(username=target.username, password=_TEMP))

    def test_canonical_platform_admin_protected_from_peer_reset(self):
        canonical, _created = User.objects.get_or_create(
            username=CANONICAL_PLATFORM_ADMIN_USERNAME,
            defaults={"is_staff": True, "is_superuser": True},
        )
        canonical.set_password("rootpass123")
        canonical.is_active = True
        canonical.save()
        # A non-canonical superuser must not be able to reset the root account here.
        self.client.post(self._url(canonical.pk), HTTP_HOST=self.host)
        canonical.refresh_from_db()
        self.assertTrue(canonical.check_password("rootpass123"))  # unchanged
