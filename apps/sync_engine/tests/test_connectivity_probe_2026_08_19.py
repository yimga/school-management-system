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
        with self.settings(RMC_HUB_BASE_URL=""):
            snap = connectivity_snapshot()
        self.assertTrue(snap["operator_base_configured"])
        self.assertIn("/api/v1/sync/bundle/download/", snap["pull_endpoint"])
