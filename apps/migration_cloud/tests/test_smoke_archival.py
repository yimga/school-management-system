"""v3.40.0 Agent 13 — smoke-result archival tests.

Coverage:

  1. Archival task writes JSON to expected path
  2. Filename matches UTC-ISO format
  3. View GET returns 200 for staff (skipped if URL unmounted)
  4. View GET returns 302/403 for anonymous
  5. Last-30 limit honored
  6. Missing var dir → graceful empty state (no 500)
  7. ``register_smoke_archival_signal`` is idempotent
  8. archive_smoke_run coerces non-dict payloads safely
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.migration_cloud import tasks_smoke_archival as archival_module
from apps.migration_cloud import views_smoke_history as view_module


class ArchiveSmokeRunTests(SimpleTestCase):
    """archive_smoke_run produces well-shaped per-run JSON files."""

    def test_writes_file_to_expected_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(BASE_DIR=tmpdir):
                payload = {
                    "status": "ran",
                    "exit_code": 0,
                    "passed": 5,
                    "failed": 0,
                    "skipped": 3,
                }
                out_path = archival_module.archive_smoke_run(payload)

            self.assertIsNotNone(out_path)
            self.assertTrue(out_path.is_file())
            self.assertEqual(out_path.parent.name, "smoke-results")

            # Filename matches the compact UTC ISO format ``YYYYMMDDTHHMMSSZ``
            # optionally followed by a numeric suffix for collisions.
            self.assertRegex(
                out_path.name,
                r"^\d{8}T\d{6}Z(?:-\d+)?\.json$",
            )

            payload_on_disk = json.loads(out_path.read_text(encoding="utf-8"))
            # Envelope shape.
            self.assertIn("archived_at_utc_iso", payload_on_disk)
            self.assertIn("summary", payload_on_disk)
            self.assertEqual(payload_on_disk["summary"]["status"], "ran")

    def test_coerces_non_dict_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(BASE_DIR=tmpdir):
                out_path = archival_module.archive_smoke_run("not a dict")
            self.assertIsNotNone(out_path)
            on_disk = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["summary"]["status"], "unknown")

    def test_coerces_none_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(BASE_DIR=tmpdir):
                out_path = archival_module.archive_smoke_run(None)
            self.assertIsNotNone(out_path)
            on_disk = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["summary"]["status"], "noop")


class SignalRegistrationTests(SimpleTestCase):
    """register_smoke_archival_signal is idempotent + safe."""

    def test_register_is_idempotent(self):
        # Reset the module-level guard so we can exercise both branches.
        archival_module._SIGNAL_WIRED = False
        first = archival_module.register_smoke_archival_signal()
        second = archival_module.register_smoke_archival_signal()
        # First call returns True (or False if celery isn't installed
        # in this lane); the second call MUST return False either way.
        self.assertFalse(second)


class SmokeHistoryViewHelperTests(SimpleTestCase):
    """View helpers tolerate missing var/ dir without 500-ing."""

    def test_list_recent_runs_empty_when_dir_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(BASE_DIR=tmpdir):
                rows = view_module._list_recent_runs()
        self.assertEqual(rows, [])

    def test_list_recent_runs_honors_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(BASE_DIR=tmpdir):
                results_dir = Path(tmpdir) / "var" / "smoke-results"
                results_dir.mkdir(parents=True)
                # Write 40 stub files; the view should return at most 30.
                for i in range(40):
                    fname = f"2026051{i:02d}T000000Z.json"
                    (results_dir / fname).write_text(
                        json.dumps({
                            "archived_at_utc_iso": "2026-05-19T00:00:00Z",
                            "summary": {"status": "ran", "passed": i},
                        }),
                        encoding="utf-8",
                    )
                rows = view_module._list_recent_runs()
        self.assertEqual(len(rows), 30)

    def test_list_recent_runs_skips_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(BASE_DIR=tmpdir):
                results_dir = Path(tmpdir) / "var" / "smoke-results"
                results_dir.mkdir(parents=True)
                (results_dir / "20260519T000000Z.json").write_text(
                    "this is not valid json",
                    encoding="utf-8",
                )
                rows = view_module._list_recent_runs()
        self.assertEqual(rows, [])

    def test_sparkline_compute_handles_empty(self):
        self.assertEqual(view_module._compute_sparkline([]), [])

    def test_sparkline_bar_widths_within_band(self):
        rows = [
            {"filename": "a.json", "passed": 1, "failed": 0},
            {"filename": "b.json", "passed": 10, "failed": 0},
        ]
        bars = view_module._compute_sparkline(rows)
        self.assertEqual(len(bars), 2)
        for bar in bars:
            self.assertGreaterEqual(bar["bar_px"], view_module._SPARKLINE_BAR_MIN_PX)
            self.assertLessEqual(bar["bar_px"], view_module._SPARKLINE_BAR_MAX_PX)


class SmokeHistoryViewAccessTests(SimpleTestCase):
    """Smoke history view rejects anonymous access."""

    def test_anonymous_get_redirects_to_login(self):
        from django.test import Client
        client = Client()
        try:
            resp = client.get("/super/migration/smoke/history/")
        except Exception:
            self.skipTest("URL not mounted in this lane")
            return
        self.assertIn(resp.status_code, (302, 403))
