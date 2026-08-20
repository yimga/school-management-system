"""The box must ask the cloud for a path that actually exists.

Reported from a live box (2026-08-20)::

    Pull: HTTP 404 - pull rejected (HTTP 404): <!doctype html> <html lang="en"
    ... data-rmc-premium-shell="tenant" ...
    - download/upload path not found: RMC_EDGE_OPERATOR_BASE is probably wrong
      or the cloud is on an older build without sync bundle APIs.

Neither hint was true. ``RMC_EDGE_OPERATOR_BASE`` pointed at the right tenant
host and the cloud was on the current build. The box was requesting
``/api/v1/sync/bundle/download/`` -- a path carried by no urlconf in the repo,
because every ``sync-*`` route lives in ``apps.api.urls``, which is mounted at
``api/``. ``/api/v1/`` maps to ``apps.api.urls_v1``, which has no sync routes.
Django matched neither, fell through to the tenant catch-all page, and returned
that page with a 404 -- so the box's own error text blamed configuration for a
hardcoded literal that had never been correct.

Seven such literals existed across five modules. The whole class of bug is that
a fallback path can silently disagree with the urlconf that defines it, and
nothing compares them. This suite is that comparison.
"""
from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import reverse

from apps.sync_engine.cloud_endpoints import (
    CLOUD_SYNC_PATHS,
    cloud_endpoint,
    cloud_path,
)


class CloudSyncPathsMatchTheUrlconfTests(SimpleTestCase):
    """The pinned literals and the urlconf must not be allowed to drift."""

    def test_every_pinned_path_equals_reverse(self):
        for url_name, pinned in sorted(CLOUD_SYNC_PATHS.items()):
            with self.subTest(url_name=url_name):
                self.assertEqual(
                    reverse(url_name),
                    pinned,
                    f"{url_name} is mounted at {reverse(url_name)!r} but "
                    f"cloud_endpoints pins {pinned!r}. A box using the pinned "
                    f"value will 404 into the tenant HTML page. Update the "
                    f"literal to match the urlconf.",
                )

    def test_no_pinned_path_uses_the_v1_prefix(self):
        """The exact mistake that shipped: /api/v1/ carries no sync routes."""
        for url_name, pinned in sorted(CLOUD_SYNC_PATHS.items()):
            with self.subTest(url_name=url_name):
                self.assertFalse(
                    pinned.startswith("/api/v1/"),
                    f"{url_name} pins {pinned!r}; /api/v1/ maps to "
                    f"apps.api.urls_v1, which declares no sync endpoints.",
                )

    def test_every_sync_route_declared_is_pinned(self):
        """A new sync endpoint must be added here, or the box cannot find it."""
        from apps.api import urls as api_urls

        declared = {
            f"api:{p.name}"
            for p in api_urls.urlpatterns
            if getattr(p, "name", None) and str(p.name).startswith("sync-")
        }
        missing = declared - set(CLOUD_SYNC_PATHS)
        self.assertEqual(
            missing,
            set(),
            f"sync route(s) {sorted(missing)} are declared in apps/api/urls.py "
            f"but absent from CLOUD_SYNC_PATHS, so a box that cannot reverse "
            f"them has no fallback.",
        )


class CloudPathResolutionTests(SimpleTestCase):
    """cloud_path prefers the live urlconf; the literal is the safety net."""

    def test_prefers_reverse_when_it_resolves(self):
        self.assertEqual(
            cloud_path("api:sync-bundle-download"),
            reverse("api:sync-bundle-download"),
        )

    def test_falls_back_to_the_pinned_literal(self):
        from unittest import mock

        from django.urls import NoReverseMatch

        with mock.patch(
            "apps.sync_engine.cloud_endpoints.reverse",
            side_effect=NoReverseMatch("no urlconf here"),
        ):
            self.assertEqual(
                cloud_path("api:sync-bundle-download"),
                "/api/sync/bundle/download/",
            )

    def test_unknown_name_raises_rather_than_building_a_bad_url(self):
        from unittest import mock

        from django.urls import NoReverseMatch

        with mock.patch(
            "apps.sync_engine.cloud_endpoints.reverse",
            side_effect=NoReverseMatch("no urlconf here"),
        ):
            with self.assertRaises(ValueError):
                cloud_path("api:sync-not-a-real-endpoint")


class CloudEndpointJoinTests(SimpleTestCase):
    """One trailing slash, never two, whatever the operator typed."""

    def test_trailing_slash_on_the_base_is_not_doubled(self):
        self.assertEqual(
            cloud_endpoint("https://t.example.com/", "api:sync-bundle-download"),
            "https://t.example.com" + reverse("api:sync-bundle-download"),
        )

    def test_bare_base_joins_cleanly(self):
        self.assertEqual(
            cloud_endpoint("https://t.example.com", "api:sync-bundle-upload"),
            "https://t.example.com" + reverse("api:sync-bundle-upload"),
        )

    def test_empty_base_yields_a_relative_path_not_a_crash(self):
        self.assertEqual(
            cloud_endpoint("", "api:sync-changes-feed"),
            reverse("api:sync-changes-feed"),
        )
