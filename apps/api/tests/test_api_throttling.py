"""Unit tests for the scoped, tenant-aware ``apps.api`` throttles.

No DB required — the throttle classes read only ``request.user``,
``request.school`` and ``request.META``, all settable on an
``APIRequestFactory`` request. We pin a fresh in-process LocMem cache via
``override_settings`` so counters don't leak between cases (and clear it
in ``setUp``).

Proven here:
  * a burst beyond the scope limit returns throttled (429-equivalent),
    under the limit succeeds;
  * one tenant's burst does NOT throttle another tenant (fairness /
    isolation);
  * read vs write scopes are budgeted independently;
  * anonymous callers on the public throttle are keyed per-IP and a
    different IP gets a fresh budget;
  * the soft-warn flag is set once the caller crosses 80% of the budget.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from rest_framework.test import APIRequestFactory

from apps.api.throttling import (
    API_PUBLIC_READ_RATE,
    API_READ_RATE,
    API_WRITE_RATE,
    ApiPublicReadThrottle,
    ApiReadThrottle,
    ApiReadWriteThrottle,
    ApiWriteThrottle,
    SOFT_WARN_FRACTION,
)

_LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "api-throttle-tests",
    }
}


def _auth_user(pk: int):
    """Minimal stand-in: the throttle only reads ``is_authenticated`` + ``pk``."""
    return SimpleNamespace(pk=pk, is_authenticated=True)


def _rate_num(rate: str) -> int:
    return int(rate.split("/")[0])


@override_settings(CACHES=_LOCMEM)
class _ThrottleTestBase(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        self.view = SimpleNamespace(throttle_scope=None)

    def _request(self, *, method="get", user=None, school_pk=None, ip="10.0.0.1"):
        builder = getattr(self.factory, method.lower())
        request = builder("/api/v1/anything", REMOTE_ADDR=ip)
        request.user = user if user is not None else SimpleNamespace(
            pk=None, is_authenticated=False
        )
        request.school = SimpleNamespace(pk=school_pk) if school_pk else None
        return request

    def _drain(self, throttle_cls, *, n, **req_kwargs):
        """Fire ``n`` requests through a FRESH throttle instance each time
        (DRF instantiates the throttle per request) and return the list of
        allow_request booleans."""
        results = []
        for _ in range(n):
            throttle = throttle_cls()
            req = self._request(**req_kwargs)
            results.append(throttle.allow_request(req, self.view))
        return results


class ApiReadThrottleTests(_ThrottleTestBase):
    def test_under_limit_allows(self):
        user = _auth_user(1)
        limit = _rate_num(API_READ_RATE)
        results = self._drain(
            ApiReadThrottle, n=limit, user=user, school_pk=1
        )
        self.assertTrue(all(results), "all requests under the limit should pass")

    def test_burst_beyond_limit_is_throttled(self):
        user = _auth_user(1)
        limit = _rate_num(API_READ_RATE)
        results = self._drain(
            ApiReadThrottle, n=limit + 5, user=user, school_pk=1
        )
        self.assertTrue(all(results[:limit]), "first <limit> should pass")
        self.assertFalse(
            any(results[limit:]), "requests beyond the limit must be throttled"
        )

    def test_anonymous_caller_not_counted_by_auth_only_read_throttle(self):
        # ApiReadThrottle is auth_only — anon callers return None key (allow).
        results = self._drain(
            ApiReadThrottle, n=_rate_num(API_READ_RATE) + 10, school_pk=1
        )
        self.assertTrue(all(results), "anon traffic is not budgeted by the auth read throttle")


class TenantIsolationTests(_ThrottleTestBase):
    def test_one_tenant_burst_does_not_throttle_another(self):
        limit = _rate_num(API_READ_RATE)
        user_a = _auth_user(100)
        user_b = _auth_user(200)

        # Tenant 1 / user A exhausts its budget.
        burst = self._drain(
            ApiReadThrottle, n=limit + 5, user=user_a, school_pk=1
        )
        self.assertFalse(burst[-1], "tenant 1 user A should be throttled after the burst")

        # Tenant 2 / user B is on a fresh budget — first request must pass.
        throttle = ApiReadThrottle()
        req_b = self._request(user=user_b, school_pk=2)
        self.assertTrue(
            throttle.allow_request(req_b, self.view),
            "tenant 2's traffic must not be throttled by tenant 1's burst",
        )

    def test_same_user_different_tenant_has_separate_budget(self):
        # Same user pk surfacing under two tenants gets independent budgets
        # (the tenant fragment is part of the cache key).
        limit = _rate_num(API_READ_RATE)
        user = _auth_user(7)
        burst = self._drain(ApiReadThrottle, n=limit + 1, user=user, school_pk=1)
        self.assertFalse(burst[-1])

        throttle = ApiReadThrottle()
        req_t2 = self._request(user=user, school_pk=2)
        self.assertTrue(throttle.allow_request(req_t2, self.view))


class ReadWriteScopeSplitTests(_ThrottleTestBase):
    def test_read_and_write_scopes_are_independent(self):
        user = _auth_user(5)
        write_limit = _rate_num(API_WRITE_RATE)

        # Exhaust the WRITE budget via the method-aware throttle.
        write_results = self._drain(
            ApiReadWriteThrottle, n=write_limit + 2, method="post",
            user=user, school_pk=1,
        )
        self.assertFalse(write_results[-1], "writes beyond write-limit are throttled")

        # READ budget is untouched — a GET still passes.
        throttle = ApiReadWriteThrottle()
        get_req = self._request(method="get", user=user, school_pk=1)
        self.assertTrue(
            throttle.allow_request(get_req, self.view),
            "read budget must be independent of the exhausted write budget",
        )

    def test_write_throttle_blocks_burst(self):
        user = _auth_user(6)
        limit = _rate_num(API_WRITE_RATE)
        results = self._drain(
            ApiWriteThrottle, n=limit + 3, method="post", user=user, school_pk=1
        )
        self.assertTrue(all(results[:limit]))
        self.assertFalse(any(results[limit:]))


class PublicReadThrottleTests(_ThrottleTestBase):
    def test_anonymous_per_ip_budget_and_isolation(self):
        limit = _rate_num(API_PUBLIC_READ_RATE)

        # IP A exhausts the public budget.
        ip_a = self._drain(ApiPublicReadThrottle, n=limit + 2, ip="203.0.113.1")
        self.assertTrue(all(ip_a[:limit]))
        self.assertFalse(any(ip_a[limit:]), "anon IP A throttled beyond the limit")

        # A different IP is on a fresh budget.
        throttle = ApiPublicReadThrottle()
        req_b = self._request(ip="203.0.113.2")
        self.assertTrue(
            throttle.allow_request(req_b, self.view),
            "a different anon IP must get a fresh budget",
        )

    def test_authenticated_caller_not_throttled_by_public_throttle(self):
        # anon_only — authenticated callers return None key (allow).
        user = _auth_user(9)
        results = self._drain(
            ApiPublicReadThrottle,
            n=_rate_num(API_PUBLIC_READ_RATE) + 5,
            user=user,
        )
        self.assertTrue(all(results), "authenticated traffic skips the anon-only throttle")


class SoftWarnTests(_ThrottleTestBase):
    def test_soft_warn_flag_set_at_80_percent(self):
        user = _auth_user(11)
        limit = _rate_num(API_READ_RATE)
        threshold = max(1, int(limit * SOFT_WARN_FRACTION))

        last_request = None
        for i in range(threshold):
            throttle = ApiReadThrottle()
            last_request = self._request(user=user, school_pk=1)
            self.assertTrue(throttle.allow_request(last_request, self.view))

        # The request that crossed the soft threshold carries the flag.
        self.assertTrue(
            getattr(last_request, "_rmc_api_rate_soft_warn", False),
            "the request crossing 80% of the budget must carry the soft-warn flag",
        )
        self.assertEqual(
            getattr(last_request, "_rmc_api_rate_scope", None),
            ApiReadThrottle.scope,
        )

    def test_no_soft_warn_well_under_threshold(self):
        user = _auth_user(12)
        throttle = ApiReadThrottle()
        req = self._request(user=user, school_pk=1)
        throttle.allow_request(req, self.view)
        self.assertFalse(getattr(req, "_rmc_api_rate_soft_warn", False))
