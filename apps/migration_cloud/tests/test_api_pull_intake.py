"""API_PULL intake adapter tests."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

from django.test import TestCase

from apps.migration_cloud.intake import get_adapter
from apps.migration_cloud.models import IntakeMethod
from apps.migration_cloud.services import BundleIngestionService, BundleSpec


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.headers.get("Authorization") != "Bearer test-token":
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps([{"id": 1, "name": "Ada"}]).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


class APIPullIntakeTests(TestCase):
    def test_api_pull_ingest(self):
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            adapter = get_adapter(IntakeMethod.API_PULL)
            handle = {
                "url": f"http://127.0.0.1:{port}/export",
                "api_token": "test-token",
                "artifact_name": "students.json",
            }
            adapter.validate_handle(handle, None)  # type: ignore[arg-type]
            svc = BundleIngestionService()
            result = svc.ingest(
                BundleSpec(
                    intake_method=IntakeMethod.API_PULL,
                    handle=handle,
                    idempotency_key="api-pull-smoke",
                )
            )
            self.assertEqual(result.artifacts_registered, 1)
        finally:
            server.shutdown()
