"""Default media STORAGES backend stays local FS unless S3 env is set."""

from __future__ import annotations

import os

from django.conf import settings
from django.test import SimpleTestCase


class MediaStorageStoragesTests(SimpleTestCase):
    def test_storages_default_present(self):
        self.assertIn("default", settings.STORAGES)

    def test_local_fs_when_s3_env_unset(self):
        if os.getenv("MEDIA_STORAGE_BACKEND", "").strip():
            self.skipTest("MEDIA_STORAGE_BACKEND set in environment")
        if os.getenv("AWS_S3_ENDPOINT_URL", "").strip() and os.getenv(
            "AWS_STORAGE_BUCKET_NAME", ""
        ).strip():
            self.skipTest("S3 endpoint + bucket set in environment")
        backend = settings.STORAGES["default"]["BACKEND"]
        self.assertEqual(backend, "django.core.files.storage.FileSystemStorage")
