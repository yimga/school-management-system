"""Tests for edge ↔ cloud connectivity diagnostics."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.sync_engine.connectivity_probe import (
    connectivity_snapshot,
    extract_http_error_detail,
    format_http_rejection,
)


class FormatHttpRejectionTests(SimpleTestCase):
    def test_502_includes_remediation_hint(self):
        msg = format_http_rejection("pull", 502, b"Bad Gateway")
        self.assertIn("pull rejected (HTTP 502)", msg)
        self.assertIn("Bad Gateway", msg)
        self.assertIn("TENANT host", msg)

    def test_json_error_body_is_parsed(self):
        body = b'{"error":"school_required","detail":"no tenant"}'
        msg = format_http_rejection("pull", 403, body)
        self.assertIn("school_required", msg)

    def test_extract_from_dict(self):
        self.assertEqual(
            extract_http_error_detail({"error": "forbidden"}),
            "forbidden",
        )


@override_settings(
    RMC_EDGE_SYNC_ENABLED=True,
    RMC_DEPLOYMENT_PROFILE="edge",
    RMC_EDGE_OPERATOR_BASE="https://gilead-tech.example.com",
)
class ConnectivitySnapshotTests(SimpleTestCase):
    def test_snapshot_includes_endpoints(self):
        """The path must be the one the cloud actually serves.

        This test used to assert ``/api/v1/sync/bundle/download/`` and had been
        FAILING ever since #183 corrected the paths — it was pinning the very bug
        that fix removed. ``apps.api.urls`` (where every ``sync-*`` route is
        declared) is mounted at ``api/`` by both config/urls.py and
        config/tenant_urls.py; ``/api/v1/`` is ``apps.api.urls_v1``, which carries
        no sync routes at all. A box asking for the v1 path gets a 404 whose body
        is a page of tenant HTML, and the error text blames the operator base.

        Asserted against ``reverse()`` rather than a second literal, so the urlconf
        stays the single authority and this cannot drift back.
        """
        from django.urls import reverse

        with self.settings(RMC_HUB_BASE_URL=""):
            snap = connectivity_snapshot()
        self.assertTrue(snap["operator_base_configured"])
        self.assertIn(reverse("api:sync-bundle-download"), snap["pull_endpoint"])
        self.assertIn(reverse("api:sync-bundle-upload"), snap["upload_endpoint"])
        self.assertNotIn("/api/v1/", snap["pull_endpoint"])
