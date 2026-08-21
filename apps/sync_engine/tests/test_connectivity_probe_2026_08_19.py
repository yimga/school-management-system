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
        """The urlconf is the authority; this test must never be one again.

        This assertion used to be the literal string ``/api/v1/sync/bundle/download/``
        and had been RED since PR #183 corrected the paths — so it was pinning the exact
        404 that fix removed. That 404 is a distinctive one: ``apps.api.urls`` (where
        every ``sync-*`` route is declared) mounts at ``/api/``, while ``/api/v1/`` is
        ``apps.api.urls_v1`` and carries no sync routes at all, so the box asked for a
        path that exists on no urlconf, Django fell through to the tenant catch-all, and
        the operator got a 404 with a page of tenant HTML in the body. Reproduced live
        against the production cloud on 2026-08-20: ``/api/sync/bundle/upload/`` answers
        ``401`` with clean problem+json, ``/api/v1/sync/bundle/download/`` answers
        ``404`` with ``<!doctype html> … data-rmc-premium-shell="tenant"``.

        Asserting against ``reverse()`` means a route that moves breaks this test
        instead of a customer's sync.
        """
        from django.urls import reverse

        with self.settings(RMC_HUB_BASE_URL=""):
            snap = connectivity_snapshot()
        self.assertTrue(snap["operator_base_configured"])
        self.assertIn(reverse("api:sync-bundle-download"), snap["pull_endpoint"])
        # And the specific wrong prefix stays named, so a regression is unmistakable.
        self.assertNotIn("/api/v1/", snap["pull_endpoint"])
