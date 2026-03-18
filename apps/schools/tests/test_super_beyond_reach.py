"""BR-04/07/09 super tools: CSV diff, governed query, legacy preview."""

import os
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class SuperBeyondReachToolsTests(TestCase):
    host = "manager.runmycampus.com"

    def setUp(self):
        self.client = Client()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        u = User.objects.create_superuser("br-super", "br@example.com", "x")
        self.client.force_login(u)

    def tearDown(self):
        self.env.stop()

    def test_migration_csv_diff_get(self):
        r = self.client.get("/super/migration/csv-diff/", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "CSV diff")

    def test_migration_csv_diff_post(self):
        a = SimpleUploadedFile(
            "a.csv", b"id,name\n1,Alice\n2,Bob", content_type="text/csv"
        )
        b = SimpleUploadedFile(
            "b.csv", b"id,name\n1,Alice\n3,Carol", content_type="text/csv"
        )
        r = self.client.post(
            "/super/migration/csv-diff/",
            {"csv_a": a, "csv_b": b, "key_column": "id"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Only in A")
        self.assertContains(r, "2")

    def test_governed_query_get_and_post(self):
        r = self.client.get("/super/tools/governed-query/", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "active_schools_count")
        r2 = self.client.post(
            "/super/tools/governed-query/",
            {"intent": "active_schools_count"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, "active_schools_count")

    def test_legacy_csv_preview_renders_cells(self):
        csv_content = b"student_id,last\n100,Smith\n200,Jones"
        f = SimpleUploadedFile("roster.csv", csv_content, content_type="text/csv")
        r = self.client.post(
            "/super/tools/legacy-csv-preview/", {"csv": f}, HTTP_HOST=self.host
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "student_id")
        self.assertContains(r, "Smith")
        self.assertContains(r, "Jones")
