"""Tests for ``services.ai_helpers_quota``.

12-pillar audit P8 follow-up. Verifies the per-tenant AI inference
quota helper:

  1. Resolves budget from tenant override → settings → default.
  2. Returns ``(allowed, remaining)`` semantics correctly.
  3. Fails open on cache outage (per security primitive convention).
  4. Treats ``override=0`` as explicit disabled (never throttles).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from services.ai_helpers_quota import (
    PLATFORM_DEFAULT_PER_DAY,
    check_inference_quota,
    get_inference_balance,
)


def _school(school_id=1, **settings):
    return SimpleNamespace(id=school_id, settings=settings or {})


class ResolveBudgetTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_default_when_no_override(self):
        ok, remaining = check_inference_quota(_school())
        self.assertTrue(ok)
        self.assertEqual(remaining, PLATFORM_DEFAULT_PER_DAY - 1)

    def test_tenant_override_takes_effect(self):
        s = _school(school_id=2, ai_inference_per_day=10)
        ok, remaining = check_inference_quota(s)
        self.assertTrue(ok)
        self.assertEqual(remaining, 9)

    def test_settings_override(self):
        with override_settings(TENANT_AI_INFERENCE_PER_DAY=50):
            ok, remaining = check_inference_quota(_school(school_id=3))
            self.assertTrue(ok)
            self.assertEqual(remaining, 49)

    def test_zero_override_disables_throttling(self):
        s = _school(school_id=4, ai_inference_per_day=0)
        # Should pass without ever touching cache.incr.
        with patch("django.core.cache.cache.incr") as mock_incr:
            ok, _ = check_inference_quota(s)
        self.assertTrue(ok)
        mock_incr.assert_not_called()


class TokenBucketTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_first_request_initializes_bucket(self):
        s = _school(school_id=10, ai_inference_per_day=3)
        ok, remaining = check_inference_quota(s)
        self.assertTrue(ok)
        self.assertEqual(remaining, 2)

    def test_request_within_budget_allowed(self):
        s = _school(school_id=11, ai_inference_per_day=3)
        for expected_remaining in (2, 1, 0):
            ok, remaining = check_inference_quota(s)
            self.assertTrue(ok, f"expected ok at remaining={expected_remaining}")
            self.assertEqual(remaining, expected_remaining)

    def test_request_over_budget_denied(self):
        s = _school(school_id=12, ai_inference_per_day=2)
        # Two allowed, the third must be denied.
        ok1, _ = check_inference_quota(s)
        ok2, _ = check_inference_quota(s)
        ok3, remaining3 = check_inference_quota(s)
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertFalse(ok3)
        self.assertEqual(remaining3, 0)

    def test_per_school_isolation(self):
        a = _school(school_id=20, ai_inference_per_day=1)
        b = _school(school_id=21, ai_inference_per_day=1)
        # Exhaust A; B must still be allowed.
        self.assertTrue(check_inference_quota(a)[0])
        self.assertFalse(check_inference_quota(a)[0])
        self.assertTrue(check_inference_quota(b)[0])


class FailOpenTests(SimpleTestCase):
    def test_cache_outage_falls_open(self):
        s = _school(school_id=30, ai_inference_per_day=1)
        # Patch the cache.incr to raise; ensure the call returns ok=True.
        with patch("django.core.cache.cache.incr", side_effect=ConnectionError):
            with patch("django.core.cache.cache.set", side_effect=ConnectionError):
                ok, _ = check_inference_quota(s)
        self.assertTrue(ok)


class GetInferenceBalanceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_balance_starts_at_budget(self):
        s = _school(school_id=40, ai_inference_per_day=100)
        self.assertEqual(get_inference_balance(s), 100)

    def test_balance_decrements_after_use(self):
        s = _school(school_id=41, ai_inference_per_day=100)
        check_inference_quota(s)
        check_inference_quota(s)
        self.assertEqual(get_inference_balance(s), 98)
