"""Tests for v3.32.0 token rotation, rate limits, and operator UI.

Two test surfaces:

  * :class:`SimpleTestCase`-style tests for URL resolution, module
    imports, scope-mapping invariants, and quota math — these run even
    when the local sqlite test DB is in a bad state (per memory
    v3.23.10).
  * :class:`TestCase`-backed tests for the DB-touching paths (rotation,
    grace period, operator-UI list view, webhook quota deferral). If
    the project's User / School factories don't import cleanly the
    individual test methods skip rather than crashing the module.

NEVER asserts on plaintext token / secret material being persisted; all
assertions are on hashes, masked previews, or short ID/scope/status
codes. ``assertLogs`` confirms the auth backend doesn't leak plaintext
on the grace path.
"""

from __future__ import annotations

import hashlib
import logging
import unittest
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone


# ─── Module / URL smoke (no DB) ───────────────────────────────────────────


class V32ModuleSmokeTests(SimpleTestCase):
    """Imports of the new modules + the new SOT additions."""

    def test_rate_limiting_imports(self):
        from apps.migration_cloud.api import rate_limiting
        self.assertTrue(hasattr(rate_limiting, "TenantRateLimiter"))
        self.assertTrue(hasattr(rate_limiting, "default_tenant_rate_limiter"))
        self.assertTrue(hasattr(rate_limiting, "MigrationCloudReadThrottle"))
        self.assertTrue(hasattr(rate_limiting, "MigrationCloudWriteThrottle"))
        self.assertGreater(rate_limiting.DEFAULT_TENANT_WEBHOOK_QUOTA_PER_HOUR, 0)
        self.assertLess(
            rate_limiting.DEFAULT_TENANT_WEBHOOK_SOFT_LIMIT,
            rate_limiting.DEFAULT_TENANT_WEBHOOK_QUOTA_PER_HOUR,
        )

    def test_token_admin_views_import(self):
        from apps.migration_cloud import views_token_admin
        self.assertTrue(hasattr(views_token_admin, "MigrationCloudTokenListView"))
        self.assertTrue(hasattr(views_token_admin, "MigrationCloudTokenMintView"))
        self.assertTrue(hasattr(views_token_admin, "MigrationCloudTokenRevokeView"))
        self.assertTrue(hasattr(views_token_admin, "MigrationCloudTokenRotateView"))

    def test_webhook_admin_views_import(self):
        from apps.migration_cloud import views_webhook_admin
        self.assertTrue(hasattr(views_webhook_admin, "MigrationCloudWebhookListView"))
        self.assertTrue(hasattr(views_webhook_admin, "MigrationCloudWebhookSubscribeView"))
        self.assertTrue(hasattr(views_webhook_admin, "MigrationCloudWebhookDeliveryLogView"))
        self.assertTrue(hasattr(views_webhook_admin, "MigrationCloudWebhookRetryView"))

    def test_deliver_due_task_wrapper(self):
        from apps.migration_cloud.api import webhook_dispatch
        self.assertTrue(hasattr(webhook_dispatch, "deliver_due_task"))
        # The shared_task decorator wraps the function but it remains callable.
        self.assertTrue(callable(webhook_dispatch.deliver_due_task))

    def test_scope_mapping_includes_rotate(self):
        from apps.migration_cloud.api.scoped_tokens import ACTION_SCOPE_REQUIREMENTS
        self.assertIn(("token", "rotate"), ACTION_SCOPE_REQUIREMENTS)
        self.assertEqual(ACTION_SCOPE_REQUIREMENTS[("token", "rotate")], "tokens:manage")

    def test_grace_period_constant(self):
        from apps.migration_cloud.api.scoped_tokens import TOKEN_ROTATION_GRACE_DAYS
        self.assertEqual(TOKEN_ROTATION_GRACE_DAYS, 7)


class V32URLResolutionTests(SimpleTestCase):
    _NS_SUPER = "migration_cloud_super"
    _NS_API_SUPER = "migration_cloud_super:migration_cloud_api"

    def test_operator_token_list_url(self):
        url = reverse(f"{self._NS_SUPER}:operator_token_list")
        self.assertIn("/operator/tokens/", url)

    def test_operator_token_mint_url(self):
        url = reverse(f"{self._NS_SUPER}:operator_token_mint")
        self.assertIn("/operator/tokens/mint/", url)

    def test_operator_token_rotate_url(self):
        url = reverse(f"{self._NS_SUPER}:operator_token_rotate", kwargs={"token_id": 7})
        self.assertIn("/operator/tokens/7/rotate/", url)

    def test_operator_webhook_list_url(self):
        url = reverse(f"{self._NS_SUPER}:operator_webhook_list")
        self.assertIn("/operator/webhooks/", url)

    def test_operator_webhook_subscribe_url(self):
        url = reverse(f"{self._NS_SUPER}:operator_webhook_subscribe")
        self.assertIn("/operator/webhooks/subscribe/", url)

    def test_api_token_rotate_url(self):
        url = reverse(f"{self._NS_API_SUPER}:token-rotate", kwargs={"pk": 3})
        self.assertIn("/tokens/3/rotate/", url)


# ─── Quota math (cache-only, no DB) ───────────────────────────────────────


class TenantRateLimiterTests(SimpleTestCase):
    """Sliding-window-ish per-tenant quota — exercises the cache backend."""

    def setUp(self):
        # Defensive: clear any prior tenant counters.
        cache.clear()

    def test_initial_call_is_allowed_and_not_soft_warn(self):
        from apps.migration_cloud.api.rate_limiting import TenantRateLimiter
        limiter = TenantRateLimiter(hour_quota=10, soft_limit=8)
        decision = limiter.try_consume(tenant_id=101)
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.is_soft_warn)
        self.assertEqual(decision.current_count, 1)
        self.assertEqual(decision.reason, "tenant-quota-ok")

    def test_soft_warn_threshold(self):
        from apps.migration_cloud.api.rate_limiting import TenantRateLimiter
        limiter = TenantRateLimiter(hour_quota=10, soft_limit=8)
        for _ in range(7):
            limiter.try_consume(tenant_id=202)
        decision = limiter.try_consume(tenant_id=202)
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.is_soft_warn)
        self.assertEqual(decision.reason, "tenant-quota-warning")

    def test_hard_limit_rejects(self):
        from apps.migration_cloud.api.rate_limiting import TenantRateLimiter
        limiter = TenantRateLimiter(hour_quota=3, soft_limit=2)
        for _ in range(3):
            d = limiter.try_consume(tenant_id=303)
            self.assertTrue(d.allowed)
        d = limiter.try_consume(tenant_id=303)
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "tenant-quota-exhausted")
        self.assertGreater(d.retry_after_seconds, 0)

    def test_tenant_isolation(self):
        from apps.migration_cloud.api.rate_limiting import TenantRateLimiter
        limiter = TenantRateLimiter(hour_quota=2, soft_limit=1)
        # Exhaust tenant A.
        limiter.try_consume(tenant_id=404)
        limiter.try_consume(tenant_id=404)
        a_reject = limiter.try_consume(tenant_id=404)
        self.assertFalse(a_reject.allowed)
        # Tenant B still fresh.
        b = limiter.try_consume(tenant_id=505)
        self.assertTrue(b.allowed)
        self.assertEqual(b.current_count, 1)

    def test_reset_clears_bucket(self):
        from apps.migration_cloud.api.rate_limiting import TenantRateLimiter
        limiter = TenantRateLimiter(hour_quota=2, soft_limit=1)
        limiter.try_consume(tenant_id=606)
        limiter.try_consume(tenant_id=606)
        self.assertEqual(limiter.peek(tenant_id=606), 2)
        limiter.reset(tenant_id=606)
        self.assertEqual(limiter.peek(tenant_id=606), 0)

    def test_invalid_limits_rejected(self):
        from apps.migration_cloud.api.rate_limiting import TenantRateLimiter
        with self.assertRaises(ValueError):
            TenantRateLimiter(hour_quota=0)
        with self.assertRaises(ValueError):
            TenantRateLimiter(hour_quota=10, soft_limit=100)

    def test_next_hour_boundary_is_future(self):
        from apps.migration_cloud.api.rate_limiting import _next_hour_boundary
        now = timezone.now()
        boundary = _next_hour_boundary(now)
        self.assertGreater(boundary, now)
        self.assertEqual(boundary.minute, 0)
        self.assertEqual(boundary.second, 0)


# ─── DB-backed tests (guarded import) ─────────────────────────────────────

try:
    from django.contrib.auth import get_user_model
    from apps.migration_cloud.models import (
        MigrationCloudAPIToken,
        MigrationCloudWebhookDelivery,
        MigrationCloudWebhookSubscription,
        WebhookDeliveryStatus,
    )
    from apps.schools.models import School
    _DB_AVAILABLE = True
except Exception:  # pragma: no cover — defensive
    _DB_AVAILABLE = False


def _make_user(is_staff: bool = True):
    User = get_user_model()
    suffix = timezone.now().strftime("%H%M%S%f")
    return User.objects.create_user(
        username=f"tok-test-{suffix}",
        email=f"tok-test-{suffix}@example.com",
        password="pw",
        is_staff=is_staff,
    )


@unittest.skipUnless(_DB_AVAILABLE, "DB models unavailable in this env")
class TokenRotationDBTests(TestCase):
    """End-to-end DB tests of the rotation path."""

    def setUp(self):
        cache.clear()
        self.user = _make_user(is_staff=True)
        # Mint a source token directly to avoid HTTP plumbing.
        from apps.migration_cloud.api.scoped_tokens import (
            _generate_token_plaintext, _hash_token,
        )
        self.source_plain = _generate_token_plaintext()
        self.source = MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash=_hash_token(self.source_plain),
            name="src",
            scopes=["bundles:read"],
        )

    def test_rotation_creates_successor_and_revokes_source_with_grace(self):
        from apps.migration_cloud.api.scoped_tokens import (
            TOKEN_ROTATION_GRACE_DAYS,
            _generate_token_plaintext,
            _hash_token,
        )
        # Simulate the rotate flow (operator path; pure model ops).
        successor_plain = _generate_token_plaintext()
        successor = MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash=_hash_token(successor_plain),
            name=self.source.name + " (rotated)",
            scopes=list(self.source.scopes),
        )
        now = timezone.now()
        self.source.revoked_at = now
        self.source.grace_until = now + timedelta(days=TOKEN_ROTATION_GRACE_DAYS)
        self.source.rotated_to = successor
        self.source.save()

        self.source.refresh_from_db()
        self.assertIsNotNone(self.source.revoked_at)
        self.assertIsNotNone(self.source.grace_until)
        self.assertEqual(self.source.rotated_to_id, successor.pk)
        # Successor is active; source is in grace.
        self.assertTrue(successor.is_active)
        self.assertFalse(self.source.is_active)  # is_active checks revoked_at

    def test_rotated_to_back_reference(self):
        successor = MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash="0" * 64,
            name="succ",
            scopes=["bundles:read"],
        )
        self.source.rotated_to = successor
        self.source.save()
        # Reverse accessor — successor knows it came from source.
        self.assertEqual(successor.rotated_from.count(), 1)
        self.assertEqual(successor.rotated_from.first().pk, self.source.pk)


@unittest.skipUnless(_DB_AVAILABLE, "DB models unavailable in this env")
class TokenAuthBackendGracePeriodTests(TestCase):
    """The auth backend respects grace_until on a revoked token."""

    def setUp(self):
        cache.clear()
        self.user = _make_user(is_staff=False)

    def _build_request(self, plaintext: str):
        from django.http import HttpRequest
        req = HttpRequest()
        req.META["HTTP_AUTHORIZATION"] = f"Token {plaintext}"
        return req

    def test_revoked_token_within_grace_still_authenticates(self):
        from apps.migration_cloud.api.scoped_tokens import (
            MigrationCloudScopedTokenAuthentication,
            _generate_token_plaintext,
            _hash_token,
        )
        plain = _generate_token_plaintext()
        now = timezone.now()
        token_row = MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash=_hash_token(plain),
            name="grace",
            scopes=["bundles:read"],
            revoked_at=now,
            grace_until=now + timedelta(days=1),
        )
        backend = MigrationCloudScopedTokenAuthentication()
        with self.assertLogs("apps.migration_cloud.api.scoped_tokens", level="INFO") as cm:
            result = backend.authenticate(self._build_request(plain))
        self.assertIsNotNone(result)
        # Logger fires the grace deprecation hint but NEVER plaintext.
        joined = " ".join(cm.output)
        self.assertIn("token_grace_used", joined)
        self.assertNotIn(plain, joined)

    def test_revoked_token_after_grace_rejected(self):
        from rest_framework.exceptions import AuthenticationFailed
        from apps.migration_cloud.api.scoped_tokens import (
            MigrationCloudScopedTokenAuthentication,
            _generate_token_plaintext,
            _hash_token,
        )
        plain = _generate_token_plaintext()
        past = timezone.now() - timedelta(days=10)
        MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash=_hash_token(plain),
            name="expired-grace",
            scopes=["bundles:read"],
            revoked_at=past,
            grace_until=past + timedelta(days=1),  # grace ended 9d ago
        )
        backend = MigrationCloudScopedTokenAuthentication()
        with self.assertRaises(AuthenticationFailed):
            backend.authenticate(self._build_request(plain))

    def test_revoked_token_no_grace_rejected(self):
        from rest_framework.exceptions import AuthenticationFailed
        from apps.migration_cloud.api.scoped_tokens import (
            MigrationCloudScopedTokenAuthentication,
            _generate_token_plaintext,
            _hash_token,
        )
        plain = _generate_token_plaintext()
        MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash=_hash_token(plain),
            name="no-grace",
            scopes=["bundles:read"],
            revoked_at=timezone.now(),
            grace_until=None,
        )
        backend = MigrationCloudScopedTokenAuthentication()
        with self.assertRaises(AuthenticationFailed):
            backend.authenticate(self._build_request(plain))


@unittest.skipUnless(_DB_AVAILABLE, "DB models unavailable in this env")
class WebhookQuotaDispatchTests(TestCase):
    """Dispatcher defers (not fails) deliveries when tenant quota is exhausted."""

    def setUp(self):
        cache.clear()
        self.user = _make_user(is_staff=False)
        self.school = School.objects.create(name="Quota School", code="quota-s")
        self.sub = MigrationCloudWebhookSubscription.objects.create(
            tenant=self.school,
            url="https://example.com/hook",
            secret_hash="0" * 64,
            secret_ciphertext=b"shh-secret-not-for-logs",
            created_by=self.user,
        )

    def _make_delivery(self):
        return MigrationCloudWebhookDelivery.objects.create(
            subscription=self.sub,
            event_type="bundle.advanced",
            payload_json={"hello": "world"},
            attempt_count=0,
            status=WebhookDeliveryStatus.PENDING,
            next_retry_at=timezone.now() - timedelta(seconds=1),
        )

    def test_delivery_deferred_when_quota_exhausted(self):
        # Saturate the tenant bucket BEFORE dispatch runs.
        from apps.migration_cloud.api.rate_limiting import (
            default_tenant_rate_limiter,
        )
        # Use a tight limiter for the test by monkeypatching the module-level
        # default — we own the singleton.
        from apps.migration_cloud.api import rate_limiting
        tight = rate_limiting.TenantRateLimiter(hour_quota=1, soft_limit=1)
        # Consume the only slot.
        first = tight.try_consume(tenant_id=self.school.pk)
        self.assertTrue(first.allowed)
        row = self._make_delivery()
        with mock.patch.object(rate_limiting, "default_tenant_rate_limiter", tight), \
             mock.patch(
                 "apps.migration_cloud.api.webhook_dispatch._deliver_one"
             ) as deliver_mock:
            from apps.migration_cloud.api.webhook_dispatch import deliver_due
            summary = deliver_due()
        # Dispatcher did NOT attempt delivery (quota exhausted).
        deliver_mock.assert_not_called()
        self.assertEqual(summary["deferred"], 1)
        self.assertEqual(summary["delivered"], 0)
        row.refresh_from_db()
        self.assertEqual(row.status, WebhookDeliveryStatus.PENDING)
        self.assertEqual(row.attempt_count, 0)
        self.assertEqual(row.deferred_reason, "tenant-quota-exhausted")
        self.assertIsNotNone(row.deferred_until)

    def test_delivery_attempted_when_quota_ok(self):
        from apps.migration_cloud.api import rate_limiting
        loose = rate_limiting.TenantRateLimiter(hour_quota=1000, soft_limit=800)
        row = self._make_delivery()
        with mock.patch.object(rate_limiting, "default_tenant_rate_limiter", loose), \
             mock.patch(
                 "apps.migration_cloud.api.webhook_dispatch._deliver_one",
                 return_value=True,
             ) as deliver_mock:
            from apps.migration_cloud.api.webhook_dispatch import deliver_due
            summary = deliver_due()
        deliver_mock.assert_called_once()
        self.assertEqual(summary["delivered"], 1)
        self.assertEqual(summary["deferred"], 0)


@unittest.skipUnless(_DB_AVAILABLE, "DB models unavailable in this env")
class OperatorTokenUITests(TestCase):
    """Staff-only access + mint round-trip on the operator screens."""

    def setUp(self):
        cache.clear()
        self.staff = _make_user(is_staff=True)
        self.non_staff = _make_user(is_staff=False)
        self.client.force_login(self.staff)

    def test_token_list_requires_staff(self):
        self.client.logout()
        self.client.force_login(self.non_staff)
        url = reverse("migration_cloud_super:operator_token_list")
        resp = self.client.get(url)
        # staff_member_required redirects non-staff to admin login (302/403).
        self.assertIn(resp.status_code, (302, 403))

    def test_token_list_staff_200(self):
        url = reverse("migration_cloud_super:operator_token_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_token_mint_get_form(self):
        url = reverse("migration_cloud_super:operator_token_mint")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Mint", resp.content)

    def test_token_mint_post_creates_and_shows_once(self):
        url = reverse("migration_cloud_super:operator_token_mint")
        resp = self.client.post(url, {
            "name": "ops-key",
            "scopes": ["bundles:read"],
        })
        self.assertEqual(resp.status_code, 200)
        # Plaintext token visible on the result page.
        self.assertIn(b"mc_", resp.content)
        # Row landed in the DB with no plaintext stored.
        rows = MigrationCloudAPIToken.objects.filter(name="ops-key")
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        # token_hash is sha256(plaintext) — 64 hex chars, never the plaintext.
        self.assertEqual(len(row.token_hash), 64)
        self.assertNotIn("mc_", row.token_hash)
