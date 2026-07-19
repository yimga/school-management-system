"""M20 — the DRF default throttle must actually throttle.

``REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]`` held only
``MigrationCloudGlobalThrottle``, whose ``allow_request()`` deliberately returns
True for any request whose path is not ``/migration/api/v1/...``. So the settings
block LOOKED like a blanket throttle while, for every other DRF view that did not
declare its own ``throttle_classes``, it was a no-op — those endpoints were
completely unthrottled (default-open).

These tests pin the backstop: the default set must contain a class that actually
budgets ordinary (non-Migration-Cloud) traffic, for both authenticated and
anonymous callers, and it must not loosen the tighter scoped budgets.
"""

from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.api.throttling import (
    API_BACKSTOP_ANON_RATE,
    API_BACKSTOP_USER_RATE,
    ApiPublicReadThrottle,
    DefaultBackstopAnonThrottle,
    DefaultBackstopUserThrottle,
)


class DefaultThrottleSetTests(TestCase):
    def test_default_throttle_classes_include_a_real_backstop(self):
        from django.conf import settings

        classes = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES") or ()
        self.assertIn("apps.api.throttling.DefaultBackstopUserThrottle", classes)
        self.assertIn("apps.api.throttling.DefaultBackstopAnonThrottle", classes)

    def test_backstops_are_importable_and_rated(self):
        # A throttle whose get_rate() returns None silently allows everything.
        self.assertEqual(DefaultBackstopUserThrottle().get_rate(), API_BACKSTOP_USER_RATE)
        self.assertEqual(DefaultBackstopAnonThrottle().get_rate(), API_BACKSTOP_ANON_RATE)
        self.assertIsNotNone(DefaultBackstopUserThrottle().get_rate())
        self.assertIsNotNone(DefaultBackstopAnonThrottle().get_rate())


class BackstopBudgetTests(TestCase):
    """The backstop must actually deny past its budget on an ordinary path."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.factory = RequestFactory()

    def _anon_request(self, path="/api/v1/anything/"):
        req = self.factory.get(path)
        req.user = None
        req.school = None
        return req

    def test_anon_backstop_denies_past_its_budget_on_a_non_migration_path(self):
        throttle = DefaultBackstopAnonThrottle()
        # num_requests parsed from the rate; drain the bucket then expect a deny.
        limit = throttle.num_requests
        self.assertGreater(limit, 0)
        req = self._anon_request()
        allowed = 0
        for _ in range(limit):
            if DefaultBackstopAnonThrottle().allow_request(req, None):
                allowed += 1
        self.assertEqual(allowed, limit, "every in-budget request should pass")
        # The next one is over budget -> denied. This is the assertion that fails
        # when the default set has no real backstop.
        self.assertFalse(
            DefaultBackstopAnonThrottle().allow_request(req, None),
            "anonymous traffic past the backstop budget must be denied",
        )

    def test_backstop_does_not_loosen_the_tighter_scoped_budget(self):
        # The public-catalog throttle is deliberately stricter than the backstop;
        # a view declaring it must keep that stricter budget.
        self.assertLess(
            ApiPublicReadThrottle().num_requests,
            DefaultBackstopAnonThrottle().num_requests,
            "scoped public-read budget must stay tighter than the global backstop",
        )
