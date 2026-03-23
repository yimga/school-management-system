from io import StringIO
from pathlib import Path
from unittest import mock
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.portal.models_kb import KBArticle, KBCategory


User = get_user_model()


class GenerateKbOdtCommandTests(TestCase):
    def setUp(self):
        self.tmp_media = Path(tempfile.mkdtemp(prefix="kb_media_"))
        self.category = KBCategory.objects.create(
            name="Operator Manual", slug="operator-manual"
        )
        self.author = User.objects.create_user(username="kb_admin", password="pass123")
        self.article = KBArticle.objects.create(
            title="Teacher Onboarding",
            slug="teacher-onboarding",
            category=self.category,
            summary="How to onboard teachers",
            content="# Teacher Onboarding\n\n## Step 1\nDo this.",
            status="PUBLISHED",
            author=self.author,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_media, ignore_errors=True)

    @override_settings(MEDIA_ROOT="")
    def test_dry_run_lists_articles(self):
        out = StringIO()
        # Scope to this test's article — DB may contain other published KB rows from fixtures.
        call_command(
            "generate_kb_odt",
            "--article-slug",
            "teacher-onboarding",
            "--formats",
            "odt,docx",
            "--dry-run",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Would process 1 article(s)", output)
        self.assertIn("teacher-onboarding", output)

    @mock.patch("apps.portal.management.commands.generate_kb_odt.markdown_to_document")
    def test_generates_odt_and_docx_exports(self, markdown_to_document_mock):
        markdown_to_document_mock.side_effect = lambda content, **kwargs: (
            f"{kwargs['output_format']}:{kwargs['title']}".encode("utf-8")
        )

        export_dir = self.tmp_media / "exports"
        out = StringIO()

        with override_settings(MEDIA_ROOT=str(self.tmp_media)):
            call_command(
                "generate_kb_odt",
                "--article-slug",
                "teacher-onboarding",
                "--formats",
                "odt,docx",
                "--engine",
                "pandoc",
                "--overwrite",
                "--export-dir",
                str(export_dir),
                stdout=out,
            )

        self.article.refresh_from_db()
        self.assertTrue(self.article.odt_file.name.endswith("teacher-onboarding.odt"))
        self.assertTrue((export_dir / "teacher-onboarding.odt").exists())
        self.assertTrue((export_dir / "teacher-onboarding.docx").exists())

        output = out.getvalue()
        self.assertIn("ODT generated: 1", output)
        self.assertIn("DOCX generated:1", output)
