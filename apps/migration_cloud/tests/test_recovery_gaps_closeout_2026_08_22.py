"""Migration Cloud recovery gap closeout — REST quarantine, tenant SSE, archive, AI explain.

Locks the four roadmap items called out after the held-row workspace wave:
  * REST API for quarantine list / resolve / export / ai-explain
  * Tenant SSE progress stream route (parity with operator)
  * Archive source files UI + manual purge after RECONCILED
  * AI explain button wired in held table
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.migration_cloud.models import BundleStatus


class RecoveryGapURLTests(SimpleTestCase):
    def test_tenant_sse_route_declared(self):
        src = Path("apps/migration_cloud/urls_connectors.py").read_text(encoding="utf-8")
        self.assertIn("bundle-progress-stream", src)
        self.assertIn("TenantMigrationProgressStreamView", src)
        url = reverse(
            "migration_cloud_connector:bundle-progress-stream",
            kwargs={"bundle_id": 3},
            urlconf="config.tenant_urls",
        )
        self.assertIn("/bundle/3/progress/stream/", url)

    def test_tenant_ai_explain_route_declared(self):
        url = reverse(
            "migration_cloud_connector:bundle-ai-explain",
            kwargs={"bundle_id": 5},
            urlconf="config.tenant_urls",
        )
        self.assertIn("/bundle/5/ai-explain/", url)

    def test_tenant_archive_route_declared(self):
        url = reverse(
            "migration_cloud_connector:bundle-archive-source",
            kwargs={"bundle_id": 9},
            urlconf="config.tenant_urls",
        )
        self.assertIn("/bundle/9/archive-source/", url)

    def test_api_quarantine_list_url_resolves(self):
        url = reverse("migration_cloud_super:migration_cloud_api:bundle-quarantine-list", kwargs={"pk": 1})
        self.assertIn("/bundles/1/quarantine/", url)

    def test_api_quarantine_resolve_url_resolves(self):
        url = reverse(
            "migration_cloud_super:migration_cloud_api:bundle-quarantine-resolve",
            kwargs={"pk": 1},
        )
        self.assertIn("/bundles/1/quarantine/resolve/", url)

    def test_api_quarantine_export_url_resolves(self):
        url = reverse(
            "migration_cloud_super:migration_cloud_api:bundle-quarantine-export",
            kwargs={"pk": 1},
        )
        self.assertIn("/bundles/1/quarantine/export/", url)

    def test_api_ai_explain_url_resolves(self):
        url = reverse(
            "migration_cloud_super:migration_cloud_api:bundle-ai-explain-row",
            kwargs={"pk": 1},
        )
        self.assertIn("/bundles/1/ai-explain/", url)


class RecoveryGapTemplateTests(SimpleTestCase):
    def test_held_table_has_explain_button(self):
        text = Path("templates/migration_cloud/anomaly_nudge.html").read_text(encoding="utf-8")
        self.assertIn("data-rmc-q-explain", text)
        self.assertIn("aiExplainUrl", text)

    def test_held_review_live_board_id_matches_js(self):
        text = Path("templates/migration_cloud/anomaly_nudge.html").read_text(encoding="utf-8")
        self.assertIn('id="mc-live-board"', text)
        js = Path("static/js/rmc-migration-live-import.js").read_text(encoding="utf-8")
        self.assertIn("mc-live-board", js)

    def test_operator_bundle_detail_has_archive_ui(self):
        text = Path("templates/migration_cloud/bundle_detail.html").read_text(encoding="utf-8")
        self.assertIn("archive_eligible", text)
        self.assertIn("archive_source_url", text)
        self.assertIn("Archive source files", text)

    def test_review_page_has_archive_and_sse(self):
        text = Path("templates/migration_cloud/connector/bundle_review.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-progress-stream-url", text)
        self.assertIn("Archive source files", text)
        self.assertIn("archive_source_url", text)

    def test_live_import_js_supports_sse(self):
        text = Path("static/js/rmc-migration-live-import.js").read_text(encoding="utf-8")
        self.assertIn("data-progress-stream-url", text)
        self.assertIn("EventSource", text)


class RecoveryGapScopeTests(SimpleTestCase):
    def test_scoped_token_quarantine_actions_registered(self):
        from apps.migration_cloud.api.scoped_tokens import ACTION_SCOPE_REQUIREMENTS

        self.assertEqual(ACTION_SCOPE_REQUIREMENTS[("bundle", "quarantine_list")], "bundles:read")
        self.assertEqual(ACTION_SCOPE_REQUIREMENTS[("bundle", "quarantine_resolve")], "bundles:write")
        self.assertEqual(ACTION_SCOPE_REQUIREMENTS[("bundle", "ai_explain_row")], "bundles:read")
        self.assertEqual(ACTION_SCOPE_REQUIREMENTS[("token", "scopes_catalog")], "tokens:manage")

    def test_quarantine_write_gate_helper_exported(self):
        from apps.migration_cloud.api.quarantine_actions import (
            _require_quarantine_read_access,
            _require_quarantine_write_access,
        )

        self.assertTrue(callable(_require_quarantine_write_access))
        self.assertTrue(callable(_require_quarantine_read_access))

    def test_live_import_js_parses_sse_payload(self):
        js = Path("static/js/rmc-migration-live-import.js").read_text(encoding="utf-8")
        self.assertIn("applyStreamEvent", js)
        self.assertIn("JSON.parse(ev.data)", js)


class ArchiveHelperTests(SimpleTestCase):
    def test_archive_stamps_metadata(self):
        from apps.migration_cloud.artifact_blob_store import archive_bundle_source_files

        bundle = SimpleNamespace(
            pk=12,
            size_summary={},
            save=mock.Mock(),
        )
        with mock.patch(
            "apps.migration_cloud.artifact_blob_store.purge_source_blobs_for_bundle",
            return_value=3,
        ):
            with mock.patch(
                "apps.migration_cloud.artifact_blob_store.source_blob_count",
                return_value=0,
            ):
                outcome = archive_bundle_source_files(bundle, actor_id=7)
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["deleted"], 3)
        self.assertIn("source_archived_at", bundle.size_summary)
        bundle.save.assert_called_once()


class TenantSSEViewSmokeTests(SimpleTestCase):
    @mock.patch("apps.migration_cloud.views_tenant_upload._tenant_bundle_or_404")
    @mock.patch("apps.migration_cloud.views_tenant_upload.user_is_tenant_admin", return_value=True)
    @mock.patch("apps.migration_cloud.progress.stream_events_since")
    def test_sse_stream_yields_connected(self, stream_mock, _admin_mock, bundle_mock):
        from apps.migration_cloud.views_tenant_upload import TenantMigrationProgressStreamView

        bundle_mock.return_value = SimpleNamespace(pk=4)
        stream_mock.return_value = iter([(1, {"kind": "stage", "message": "ok"})])
        request = RequestFactory().get("/bundle/4/progress/stream/")
        request.user = SimpleNamespace(is_authenticated=True)
        response = TenantMigrationProgressStreamView.as_view()(request, bundle_id=4)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        chunks = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn(": connected", chunks)
        self.assertIn("data:", chunks)


class TenantAIExplainSmokeTests(SimpleTestCase):
    @mock.patch("apps.migration_cloud.views_tenant_upload._tenant_bundle_or_404")
    @mock.patch("apps.migration_cloud.views_tenant_upload.user_is_tenant_admin", return_value=True)
    @mock.patch("apps.migration_cloud.ai_bridge.explain_quarantine_row")
    def test_ai_explain_returns_json(self, explain_mock, _admin_mock, bundle_mock):
        from apps.migration_cloud.views_tenant_upload import TenantMigrationAIExplainView

        bundle_mock.return_value = SimpleNamespace(pk=2, school=SimpleNamespace(pk=1))
        proposal = SimpleNamespace(answer="The class name was missing.", confidence=0.9)
        explain_mock.return_value = proposal
        request = RequestFactory().post(
            "/bundle/2/ai-explain/",
            data='{"row": {"name": "Jane"}, "reason": "missing class"}',
            content_type="application/json",
        )
        request.user = SimpleNamespace(is_authenticated=True, pk=1)
        response = TenantMigrationAIExplainView.as_view()(request, bundle_id=2)
        self.assertEqual(response.status_code, 200)
        import json

        payload = json.loads(response.content.decode("utf-8"))
        self.assertTrue(payload["ai_available"])
        self.assertIn("class", payload["explanation"].lower())
