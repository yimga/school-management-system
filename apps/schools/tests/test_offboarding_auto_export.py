"""O3: the portability export is generated automatically on closure request.

Previously a tenant had to click "Generate Export" after requesting closure; if
they forgot, the archive was never produced and was lost after the grace window.
Now the export is triggered the instant closure is requested.

The export itself is exercised by its own tests; here we assert the WIRING — that
``request_self_service_closure`` invokes it and reports readiness — so the test
stays fast and does not walk the whole tenant on every run.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.schools import tenant_offboarding as to
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig

User = get_user_model()


class AutoExportOnClosureTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="AutoExport School",
            slug="autoexport-school",
            subdomain="autoexport-school",
            is_active=True,
            is_approved=True,
            default_region=RegionConfig.get_default(),
        )
        self.user = User.objects.create_user(
            username="o3_admin", password="x", role=User.Role.ADMIN
        )

    def test_closure_request_auto_generates_export(self):
        fake = to.ExportResult(
            archive_dir="/tmp/x",
            export_zip_path="/tmp/x/portability_export.zip",
            student_export_count=0,
            manifest_path="/tmp/x/manifest.json",
        )
        with mock.patch.object(to, "run_wind_down_export", return_value=fake) as m:
            result = to.request_self_service_closure(
                self.school, actor=self.user, acknowledge=True
            )
        m.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertTrue(
            result["export_ready"], "closure must auto-generate the portability export"
        )

    def test_export_failure_never_blocks_closure(self):
        with mock.patch.object(
            to, "run_wind_down_export", side_effect=RuntimeError("disk full")
        ):
            result = to.request_self_service_closure(
                self.school, actor=self.user, acknowledge=True
            )
        # Closure still succeeds; export simply not ready (manual button remains).
        self.assertTrue(result["ok"])
        self.assertFalse(result["export_ready"])

    def test_closure_requires_acknowledgement(self):
        with self.assertRaises(ValueError):
            to.request_self_service_closure(self.school, actor=self.user, acknowledge=False)
