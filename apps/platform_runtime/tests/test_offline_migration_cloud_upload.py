"""Offline Migration Cloud upload SODP applier + capability wiring."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.platform_runtime.offline_action_types import (
    OfflineActionType,
    validate_offline_payload,
)
from apps.platform_runtime.offline_queue import _apply_migration_cloud_upload
from apps.schools.models import School
from apps.siteconfig.tests._template_nodes import assert_markup

UPLOAD_TPL = Path("templates/migration_cloud/connector/upload.html")


class MigrationCloudOfflineValidationTests(SimpleTestCase):
    def test_requires_filenames_and_client_id(self):
        errs = validate_offline_payload(
            OfflineActionType.MIGRATION_BUNDLE_UPLOAD,
            {},
        )
        self.assertTrue(any("filenames" in e for e in errs))
        self.assertTrue(any("client_offline_id" in e for e in errs))

    def test_forbids_base64_blob_keys(self):
        errs = validate_offline_payload(
            OfflineActionType.MIGRATION_BUNDLE_UPLOAD,
            {
                "filenames": ["a.csv"],
                "client_offline_id": "mc-1",
                "file_base64": "AAAA",
            },
        )
        self.assertTrue(any("file_base64" in e for e in errs))


@override_settings(ALLOWED_HOSTS=["*"])
class MigrationCloudOfflineApplyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="MC Offline School",
            slug="mc-offline-school",
            subdomain="mc-offline-school",
            is_active=True,
        )

    def test_metadata_only_parks_intent(self):
        result = _apply_migration_cloud_upload(
            self.school.pk,
            1,
            {
                "filenames": ["students.csv"],
                "sizes": [12],
                "client_offline_id": "mc-offline-abc",
                "label": "night sync",
            },
        )
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("pending_files"))
        self.school.refresh_from_db()
        intents = (self.school.settings or {}).get("migration_cloud", {}).get(
            "offline_upload_intents"
        ) or []
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]["client_offline_id"], "mc-offline-abc")

    def test_dedup_same_client_offline_id(self):
        payload = {
            "filenames": ["students.csv"],
            "client_offline_id": "mc-offline-dup",
        }
        self.assertTrue(_apply_migration_cloud_upload(self.school.pk, 1, payload)["ok"])
        again = _apply_migration_cloud_upload(self.school.pk, 1, payload)
        self.assertTrue(again.get("dedup"))

    @mock.patch("apps.migration_cloud.services.BundleIngestionService.ingest")
    def test_staged_paths_call_ingest(self, mock_ingest):
        mock_ingest.return_value = SimpleNamespace(
            bundle_id=99, artifacts_registered=1
        )
        with mock.patch(
            "apps.migration_cloud.celery_tasks.enqueue_advance",
            return_value="task",
        ):
            result = _apply_migration_cloud_upload(
                self.school.pk,
                1,
                {
                    "filenames": ["students.csv"],
                    "client_offline_id": "mc-staged-1",
                    "staged_media_paths": ["/tmp/students.csv"],
                },
            )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("bundle_id"), 99)
        mock_ingest.assert_called_once()


class MigrationCloudOfflineWiringMarkers(SimpleTestCase):
    def test_upload_template_and_js_tokens(self):
        tpl = Path("templates/migration_cloud/connector/upload.html").read_text(
            encoding="utf-8"
        )
        # rmc-offline-portal-forms.js finds the form by querying for this
        # attribute, so it has to be ON the emitted element; the two .js needles
        # below are file reads because a script has no template to parse.
        assert_markup(self, UPLOAD_TPL, 'data-rmc-offline-form="migration_cloud_upload"')
        self.assertIn('data-rmc-offline-form="migration_cloud_upload"', tpl)
        js = Path("static/js/rmc-offline-portal-forms.js").read_text(encoding="utf-8")
        self.assertIn("migration_cloud_upload", js)
        self.assertIn("wireMigrationCloudUpload", js)
