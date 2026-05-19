"""Tests for v3.33.0 REST API globalization + operator UX completion.

Five surfaces under test:

1. ``MigrationCloudGlobalThrottle.allow_request`` activates ONLY for
   paths matching ``/migration/api/v1/``; non-/api/v1/ paths short-
   circuit through and return True.
2. ``SoftWarnHeaderMiddleware`` paints ``X-RateLimit-Soft-Warn: 1``
   when the throttle flags >=80% bucket utilization.
3. The standalone webhook verifier SDK (Python) accepts a known-good
   signature and rejects a known-bad one, in constant time.
4. The ``token_rotation_chain.html`` template renders a 3-link chain
   for an anchor token whose lineage is A -> B -> C.
5. The verifier-asset download endpoints serve the SDK files with the
   right ``Content-Disposition`` attachment headers.

Each test guards against missing DB models so the file is importable
even when the local sqlite test DB is in a bad state (per memory
v3.23.10 precedent).
"""

from __future__ import annotations

import unittest
from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone


# ─── 1) Throttle path-scope tests ────────────────────────────────────────


class _StubRequest:
    """Plain-object stand-in for an HttpRequest.

    We avoid ``mock.Mock`` because Mock auto-creates child attributes on
    access — which defeats every ``getattr(req, "_rmc_rate_soft_warn",
    False)`` falsy check we make (Mock objects are truthy).
    """

    def __init__(self, path: str, method: str = "GET"):
        self.path = path
        self.method = method
        self.auth = None
        self.META = {"REMOTE_ADDR": "127.0.0.1"}
        class _U:
            is_authenticated = False
            pk = None
        self.user = _U()


class GlobalThrottlePathScopeTests(SimpleTestCase):
    """``allow_request`` skips for non-/api/v1/ paths."""

    def _fake_request(self, path: str, method: str = "GET"):
        return _StubRequest(path, method)

    def test_throttle_skips_super_dashboard_path(self):
        from apps.migration_cloud.api.rate_limiting import (
            MigrationCloudGlobalThrottle,
        )
        throttle = MigrationCloudGlobalThrottle()
        req = self._fake_request("/super/")
        self.assertTrue(throttle.allow_request(req, view=None))

    def test_throttle_skips_marketing_path(self):
        from apps.migration_cloud.api.rate_limiting import (
            MigrationCloudGlobalThrottle,
        )
        throttle = MigrationCloudGlobalThrottle()
        req = self._fake_request("/")
        self.assertTrue(throttle.allow_request(req, view=None))

    def test_throttle_skips_admin_api_path(self):
        # Other /api/v1/ surfaces (non-migration-cloud) MUST be skipped.
        from apps.migration_cloud.api.rate_limiting import (
            MigrationCloudGlobalThrottle,
        )
        throttle = MigrationCloudGlobalThrottle()
        req = self._fake_request("/api/v1/billing/")
        self.assertTrue(throttle.allow_request(req, view=None))

    def test_throttle_activates_on_migration_api_path(self):
        from apps.migration_cloud.api.rate_limiting import (
            MigrationCloudGlobalThrottle,
        )
        throttle = MigrationCloudGlobalThrottle()
        req = self._fake_request(
            "/super/migration/api/v1/bundles/", method="GET",
        )
        # First request through the throttle: allowed AND scope set.
        from django.core.cache import cache
        cache.clear()
        allowed = throttle.allow_request(req, view=None)
        self.assertTrue(allowed)
        self.assertEqual(throttle.scope, "bundles_read")

    def test_throttle_picks_write_scope_for_post(self):
        from apps.migration_cloud.api.rate_limiting import (
            MigrationCloudGlobalThrottle,
        )
        from django.core.cache import cache
        cache.clear()
        throttle = MigrationCloudGlobalThrottle()
        req = self._fake_request(
            "/portal/configure/migration/api/v1/bundles/", method="POST",
        )
        throttle.allow_request(req, view=None)
        self.assertEqual(throttle.scope, "bundles_write")

    def test_throttle_picks_webhook_scope_for_webhooks_path(self):
        from apps.migration_cloud.api.rate_limiting import (
            MigrationCloudGlobalThrottle,
        )
        from django.core.cache import cache
        cache.clear()
        throttle = MigrationCloudGlobalThrottle()
        req = self._fake_request(
            "/super/migration/api/v1/webhooks/", method="POST",
        )
        throttle.allow_request(req, view=None)
        self.assertEqual(throttle.scope, "webhook_tenant")

    def test_scope_for_request_helper_returns_none_off_path(self):
        from apps.migration_cloud.api.rate_limiting import _scope_for_request
        req = self._fake_request("/super/marketplace/")
        self.assertIsNone(_scope_for_request(req))

    def test_scope_for_request_helper_returns_none_for_other_api(self):
        from apps.migration_cloud.api.rate_limiting import _scope_for_request
        req = self._fake_request("/api/v1/billing/invoices/")
        self.assertIsNone(_scope_for_request(req))


# ─── 2) Soft-warn header tests ───────────────────────────────────────────


class GlobalThrottleSoftWarnTests(SimpleTestCase):
    """Throttle flags request._rmc_rate_soft_warn at >=80% utilization."""

    def _req(self, path="/super/migration/api/v1/bundles/", method="GET"):
        return _StubRequest(path, method)

    def test_soft_warn_flag_set_after_eighty_percent(self):
        from apps.migration_cloud.api.rate_limiting import (
            MigrationCloudGlobalThrottle,
        )
        from django.core.cache import cache
        cache.clear()
        # bundles_read rate is "100/min" — 80% threshold = 80 requests.
        throttle = MigrationCloudGlobalThrottle()
        # Spin 80 successful calls into the history; on the 81st we expect
        # the soft-warn flag to land (since 80 / 100 >= 0.80).
        for _ in range(80):
            req = self._req()
            throttle.allow_request(req, view=None)
        # 81st call — should still be allowed AND soft-warned.
        req = self._req()
        allowed = throttle.allow_request(req, view=None)
        self.assertTrue(allowed)
        self.assertTrue(getattr(req, "_rmc_rate_soft_warn", False))
        self.assertEqual(getattr(req, "_rmc_rate_scope", None), "bundles_read")

    def test_soft_warn_flag_not_set_below_threshold(self):
        from apps.migration_cloud.api.rate_limiting import (
            MigrationCloudGlobalThrottle,
        )
        from django.core.cache import cache
        cache.clear()
        throttle = MigrationCloudGlobalThrottle()
        # Just 10 requests — well below 80% of 100.
        for _ in range(10):
            req = self._req()
            throttle.allow_request(req, view=None)
        req = self._req()
        throttle.allow_request(req, view=None)
        self.assertFalse(getattr(req, "_rmc_rate_soft_warn", False))

    def test_soft_warn_middleware_paints_header(self):
        from django.http import HttpResponse
        from apps.migration_cloud.api.rate_limiting import (
            SOFT_WARN_HEADER,
            SCOPE_HEADER,
            SoftWarnHeaderMiddleware,
        )

        def view(request):
            return HttpResponse("ok")

        middleware = SoftWarnHeaderMiddleware(view)
        req = _StubRequest("/super/migration/api/v1/bundles/")
        # Pre-set the flag — simulates the throttle having run.
        req._rmc_rate_soft_warn = True
        req._rmc_rate_scope = "bundles_read"
        response = middleware(req)
        self.assertEqual(response[SOFT_WARN_HEADER], "1")
        self.assertEqual(response[SCOPE_HEADER], "bundles_read")

    def test_soft_warn_middleware_noop_without_flag(self):
        from django.http import HttpResponse
        from apps.migration_cloud.api.rate_limiting import (
            SOFT_WARN_HEADER,
            SoftWarnHeaderMiddleware,
        )

        def view(request):
            return HttpResponse("ok")

        middleware = SoftWarnHeaderMiddleware(view)
        req = _StubRequest("/super/")
        # Explicitly absent flag — middleware must not paint.
        response = middleware(req)
        self.assertNotIn(SOFT_WARN_HEADER, response)


# ─── 3) Webhook verifier SDK tests ───────────────────────────────────────


class WebhookVerifierSDKTests(SimpleTestCase):
    """Standalone Python verifier accepts good signature, rejects bad."""

    SECRET = b"whsec_test_secret_do_not_use_in_production"
    BODY = b'{"event":"bundle.applied","bundle_id":42}'

    def _good_signature(self):
        import hashlib
        import hmac
        return "sha256=" + hmac.new(
            self.SECRET, self.BODY, hashlib.sha256,
        ).hexdigest()

    def test_verifier_accepts_known_good_signature(self):
        from apps.migration_cloud.api.webhook_verifier_sdk import verify_signature
        good = self._good_signature()
        self.assertTrue(verify_signature(self.BODY, good, self.SECRET))

    def test_verifier_rejects_known_bad_signature(self):
        from apps.migration_cloud.api.webhook_verifier_sdk import verify_signature
        bad = "sha256=" + "0" * 64
        self.assertFalse(verify_signature(self.BODY, bad, self.SECRET))

    def test_verifier_rejects_wrong_prefix(self):
        from apps.migration_cloud.api.webhook_verifier_sdk import verify_signature
        wrong_prefix = "md5=" + "a" * 32
        self.assertFalse(verify_signature(self.BODY, wrong_prefix, self.SECRET))

    def test_verifier_rejects_empty_header(self):
        from apps.migration_cloud.api.webhook_verifier_sdk import verify_signature
        self.assertFalse(verify_signature(self.BODY, "", self.SECRET))
        self.assertFalse(verify_signature(self.BODY, None, self.SECRET))

    def test_verifier_rejects_wrong_secret(self):
        from apps.migration_cloud.api.webhook_verifier_sdk import verify_signature
        good = self._good_signature()
        wrong_secret = b"whsec_a_different_secret_entirely"
        self.assertFalse(verify_signature(self.BODY, good, wrong_secret))

    def test_verifier_handles_str_body(self):
        from apps.migration_cloud.api.webhook_verifier_sdk import verify_signature
        body_str = self.BODY.decode("utf-8")
        good = self._good_signature()
        self.assertTrue(verify_signature(body_str, good, self.SECRET))

    def test_verifier_handles_str_secret(self):
        from apps.migration_cloud.api.webhook_verifier_sdk import verify_signature
        secret_str = self.SECRET.decode("utf-8")
        good = self._good_signature()
        self.assertTrue(verify_signature(self.BODY, good, secret_str))

    def test_compute_signature_round_trips(self):
        from apps.migration_cloud.api.webhook_verifier_sdk import (
            compute_signature, verify_signature,
        )
        sig = compute_signature(self.BODY, self.SECRET)
        self.assertTrue(sig.startswith("sha256="))
        self.assertEqual(len(sig), len("sha256=") + 64)
        self.assertTrue(verify_signature(self.BODY, sig, self.SECRET))

    def test_verifier_uses_constant_time_compare(self):
        # Sanity: the SDK delegates to hmac.compare_digest. We assert
        # the symbol is referenced rather than timing it (timing is
        # flaky in CI). hmac.compare_digest is the only constant-time
        # primitive in the stdlib.
        import inspect
        from apps.migration_cloud.api import webhook_verifier_sdk
        src = inspect.getsource(webhook_verifier_sdk)
        self.assertIn("hmac.compare_digest", src)


# ─── 4) Token rotation chain rendering ───────────────────────────────────


try:
    from django.contrib.auth import get_user_model
    from apps.migration_cloud.models import MigrationCloudAPIToken
    _DB_AVAILABLE = True
except Exception:  # pragma: no cover — defensive
    _DB_AVAILABLE = False


@unittest.skipUnless(_DB_AVAILABLE, "DB models unavailable in this env")
class TokenRotationChainViewTests(TestCase):
    """The chain view renders a 3-link chain end-to-end."""

    def setUp(self):
        User = get_user_model()
        suffix = timezone.now().strftime("%H%M%S%f")
        self.user = User.objects.create_user(
            username=f"chain-{suffix}",
            email=f"chain-{suffix}@example.com",
            password="pw",
            is_staff=True,
        )
        # Build A -> B -> C chain. C is the latest.
        self.token_c = MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash="c" * 64,
            name="C",
            scopes=["bundles:read"],
        )
        now = timezone.now()
        self.token_b = MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash="b" * 64,
            name="B",
            scopes=["bundles:read"],
            revoked_at=now,
            grace_until=now + timedelta(days=7),
            rotated_to=self.token_c,
        )
        self.token_a = MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash="a" * 64,
            name="A",
            scopes=["bundles:read"],
            revoked_at=now - timedelta(days=14),
            grace_until=now - timedelta(days=7),
            rotated_to=self.token_b,
        )

    def test_chain_view_renders_three_links_from_middle_anchor(self):
        from apps.migration_cloud.views_token_admin import TokenRotationChainView
        view = TokenRotationChainView()
        forward = view._walk_forward(self.token_b)
        backward = view._walk_backward(self.token_b)
        self.assertEqual([t.pk for t in backward], [self.token_a.pk])
        self.assertEqual(
            [t.pk for t in forward],
            [self.token_b.pk, self.token_c.pk],
        )
        full = backward + forward
        self.assertEqual(len(full), 3)
        self.assertEqual(
            [t.pk for t in full],
            [self.token_a.pk, self.token_b.pk, self.token_c.pk],
        )

    def test_chain_view_renders_three_links_from_anchor_a(self):
        from apps.migration_cloud.views_token_admin import TokenRotationChainView
        view = TokenRotationChainView()
        forward = view._walk_forward(self.token_a)
        self.assertEqual(
            [t.pk for t in forward],
            [self.token_a.pk, self.token_b.pk, self.token_c.pk],
        )

    def test_chain_view_renders_three_links_from_anchor_c(self):
        from apps.migration_cloud.views_token_admin import TokenRotationChainView
        view = TokenRotationChainView()
        backward = view._walk_backward(self.token_c)
        self.assertEqual(
            [t.pk for t in backward],
            [self.token_a.pk, self.token_b.pk],
        )

    def test_chain_row_marks_anchor_and_grace_status(self):
        from apps.migration_cloud.views_token_admin import TokenRotationChainView
        view = TokenRotationChainView()
        row_b = view._row_for_chain(self.token_b, self.token_b.pk)
        self.assertTrue(row_b["is_anchor"])
        self.assertTrue(row_b["in_grace"])  # revoked but grace window open
        row_a = view._row_for_chain(self.token_a, self.token_b.pk)
        self.assertFalse(row_a["is_anchor"])
        self.assertFalse(row_a["in_grace"])  # grace expired

    def test_chain_walk_cycle_defense(self):
        """A pathological cycle terminates rather than looping forever."""
        from apps.migration_cloud.views_token_admin import TokenRotationChainView
        # Manually create a self-referential cycle on a throwaway row.
        cyclic = MigrationCloudAPIToken.objects.create(
            user=self.user,
            token_hash="d" * 64,
            name="cyclic",
            scopes=["bundles:read"],
        )
        # Save the FK back to self.
        cyclic.rotated_to = cyclic
        cyclic.save(update_fields=["rotated_to"])
        view = TokenRotationChainView()
        forward = view._walk_forward(cyclic)
        # Terminates at 1 step (self-cycle detected by seen_ids).
        self.assertEqual(len(forward), 1)


# ─── 5) Verifier asset download tests ────────────────────────────────────


class VerifierAssetDownloadTests(SimpleTestCase):
    """The download endpoint exposes Python, JS, and docs assets."""

    def test_url_resolves(self):
        from django.urls import reverse
        url = reverse(
            "migration_cloud_super:migration_cloud_api:webhook-verifier-download",
            kwargs={"asset": "python"},
        )
        self.assertIn("/webhooks/verifier/python/", url)

    def test_unknown_asset_returns_404(self):
        from django.http import Http404
        from apps.migration_cloud.api.urls import webhook_verifier_download
        req = _StubRequest("/x/")
        with self.assertRaises(Http404):
            webhook_verifier_download(req, asset="ruby")

    def test_python_asset_served(self):
        from apps.migration_cloud.api.urls import webhook_verifier_download
        req = _StubRequest("/x/")
        response = webhook_verifier_download(req, asset="python")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("webhook_verifier_sdk.py", response["Content-Disposition"])

    def test_javascript_asset_served(self):
        from apps.migration_cloud.api.urls import webhook_verifier_download
        req = _StubRequest("/x/")
        response = webhook_verifier_download(req, asset="javascript")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "runmycampus_webhook_verifier.js",
            response["Content-Disposition"],
        )

    def test_docs_asset_served(self):
        from apps.migration_cloud.api.urls import webhook_verifier_download
        req = _StubRequest("/x/")
        response = webhook_verifier_download(req, asset="docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "WEBHOOK_VERIFICATION.md",
            response["Content-Disposition"],
        )


# ─── 6) SSE transport-mode tests ─────────────────────────────────────────


class SSETransportModeTests(SimpleTestCase):
    """``MIGRATION_CLOUD_SSE_TRANSPORT`` switches the stream generator.

    We monkey-patch the ``settings`` attribute on the sse module rather
    than using ``override_settings``, because the latter triggers a DRF
    settings-class rebuild which (under bare ``python -m unittest``)
    hits the AppRegistryNotReady wall before django.setup() completes.
    Under ``manage.py test`` both approaches work.
    """

    def _patched(self, value):
        """Patch ``sse.settings.MIGRATION_CLOUD_SSE_TRANSPORT``.

        Returns a context manager that restores the original on exit.
        """
        from apps.migration_cloud.api import sse

        class _Ctx:
            def __enter__(_self):
                _self._original = getattr(
                    sse.settings, "MIGRATION_CLOUD_SSE_TRANSPORT", None,
                )
                # Set on the live settings object — this is read by
                # ``_resolved_transport`` via getattr, so a plain assign
                # works without poking the DRF settings cache.
                sse.settings.MIGRATION_CLOUD_SSE_TRANSPORT = value
                return _self

            def __exit__(_self, *exc):
                if _self._original is None:
                    try:
                        delattr(sse.settings, "MIGRATION_CLOUD_SSE_TRANSPORT")
                    except AttributeError:
                        pass
                else:
                    sse.settings.MIGRATION_CLOUD_SSE_TRANSPORT = _self._original
                return False

        return _Ctx()

    def test_default_transport_is_wsgi_fallback(self):
        from apps.migration_cloud.api.sse import (
            SSE_TRANSPORT_WSGI_FALLBACK, _resolved_transport,
        )
        # Stock setting (set by config/settings.py at module load).
        self.assertEqual(_resolved_transport(), SSE_TRANSPORT_WSGI_FALLBACK)

    def test_resolved_transport_honors_asgi_daphne(self):
        from apps.migration_cloud.api.sse import (
            SSE_TRANSPORT_ASGI_DAPHNE, _resolved_transport,
        )
        with self._patched("asgi-daphne"):
            self.assertEqual(_resolved_transport(), SSE_TRANSPORT_ASGI_DAPHNE)

    def test_resolved_transport_falls_back_on_invalid_value(self):
        from apps.migration_cloud.api.sse import (
            SSE_TRANSPORT_WSGI_FALLBACK, _resolved_transport,
        )
        with self._patched("not-a-real-mode"):
            self.assertEqual(_resolved_transport(), SSE_TRANSPORT_WSGI_FALLBACK)

    def test_snapshot_generator_emits_close_sentinel(self):
        from apps.migration_cloud.api.sse import _generate_snapshot

        class _Bundle:
            pk = 42
            status = "applied"
            updated_at = timezone.now()

        frames = list(_generate_snapshot(_Bundle()))
        self.assertEqual(len(frames), 2)
        joined = b"".join(frames)
        self.assertIn(b"bundle.status", joined)
        self.assertIn(b"stream.close", joined)
        self.assertIn(b"wsgi-fallback-one-shot", joined)
