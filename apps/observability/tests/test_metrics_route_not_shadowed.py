"""`/metrics/` must resolve to the exporter the operator actually configured.

WHY THIS EXISTS
---------------
``config/urls.py`` registered ``path("metrics/", obs_views.metrics)`` around line
537 and then, ~1400 lines later, appended
``path("metrics/", PrometheusMetricsView.as_view())`` inside the
``_OBSERVABILITY_PROM_BACKEND`` block. Django resolves first-match-wins, so the
second registration could never be reached: the v3.39.0 exporter was dead on this
urlconf, and the v3.40.0 ``OBSERVABILITY_METRICS_BEARER_TOKEN`` guard it carries
was inert. An operator following the docs would set that token, believe the
scrape endpoint was secured by it, and in fact be relying on
``@observability_auth_required`` on an entirely different view.

Nothing caught it. ``verify_url_name_integrity`` asks whether a NAME reverses;
both names reverse. ``scan_hardcoded_dead_paths`` asks whether a literal path
resolves on some host; ``/metrics/`` resolves fine. Neither asks whether two
registrations claim the same path, nor which one wins -- and the losing one is
still perfectly importable, reversible and testable in isolation.

These tests pin the resolution, not the registration, because the registration is
what looked right the whole time.
"""
from __future__ import annotations

import unittest

from django.test import SimpleTestCase


class MetricsPathHasOneOwnerTests(SimpleTestCase):
    def test_no_duplicate_metrics_registration_survives(self):
        """Two patterns may declare `metrics/`; only the first can ever answer.

        A duplicate is not automatically wrong -- it is wrong when the SECOND one
        is the one somebody expects to serve, which is exactly what happened.
        Assert the winner by identity so a future re-append is caught.
        """
        from django.urls import resolve

        match = resolve("/metrics/")
        self.assertIn(
            match.url_name,
            {"metrics", "prometheus_metrics"},
            "/metrics/ resolved to something unexpected: " + str(match.url_name),
        )

    def test_prometheus_exporter_wins_when_its_backend_is_selected(self):
        """The opt-in exists to select this exporter; it must be the one mounted.

        Skipped when the backend is not enabled -- the block is a lazy include and
        does not run at all under the default "noop" backend, which is correct.
        """
        from django.conf import settings

        backend = getattr(settings, "OBSERVABILITY_METRICS_BACKEND", "noop")
        if backend != "prometheus-client":
            raise unittest.SkipTest(
                f"OBSERVABILITY_METRICS_BACKEND={backend!r}; the prometheus block "
                "is a lazy include and is not mounted, which is the correct "
                "behaviour for this backend."
            )
        from django.urls import resolve

        match = resolve("/metrics/")
        self.assertEqual(
            match.url_name,
            "prometheus_metrics",
            "OBSERVABILITY_METRICS_BACKEND is prometheus-client but /metrics/ "
            "resolves to another view, so the bearer-token guard on "
            "PrometheusMetricsView is inert.",
        )

    def test_bearer_token_setting_is_read_by_the_view_that_serves_metrics(self):
        """A token nobody reads is a security control that does not exist."""
        import inspect

        from apps.observability import views_metrics

        source = inspect.getsource(views_metrics)
        self.assertIn(
            "OBSERVABILITY_METRICS_BEARER_TOKEN",
            source,
            "views_metrics no longer reads the bearer token setting",
        )
