from io import StringIO
from pathlib import Path
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.portal.models_kb import KBArticle, KBCategory


User = get_user_model()


class VerifyKbExportsCommandTests(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.mkdtemp(prefix="kb_verify_media_")
        self.category = KBCategory.objects.create(name="KB Ops", slug="kb-ops")
        self.author = User.objects.create_user(username="kb_verify", password="pass123")
        self.article = KBArticle.objects.create(
            title="Operations Manual",
            slug="operations-manual",
            category=self.category,
            summary="Ops handbook",
            content="# Operations\n\nPublished KB content.",
            status="PUBLISHED",
            author=self.author,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_media, ignore_errors=True)

    @override_settings(MEDIA_ROOT="")
    def test_verify_passes_when_odt_and_docx_exist(self):
        with override_settings(MEDIA_ROOT=self.tmp_media):
            self.article.odt_file.save("operations-manual.odt", ContentFile(b"odt-bytes"), save=True)
            export_dir = Path(self.tmp_media) / "kb" / "generated"
            export_dir.mkdir(parents=True, exist_ok=True)
            (export_dir / "operations-manual.docx").write_bytes(b"docx-bytes")

            out = StringIO()
            call_command("verify_kb_exports", "--strict", stdout=out)
            self.assertIn("KB export verification passed", out.getvalue())

    @override_settings(MEDIA_ROOT="")
    def test_verify_strict_fails_when_docx_missing(self):
        with override_settings(MEDIA_ROOT=self.tmp_media):
            self.article.odt_file.save("operations-manual.odt", ContentFile(b"odt-bytes"), save=True)

            with self.assertRaises(CommandError):
                call_command("verify_kb_exports", "--strict")
