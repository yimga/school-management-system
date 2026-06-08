from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.portal.kb_office_service import (
    html_to_plain_text,
    validate_office_extension,
)


class KbOfficeServiceUnitTests(SimpleTestCase):
    def test_validate_office_extension_accepts_odt(self):
        self.assertEqual(validate_office_extension("guide.odt"), ".odt")

    def test_validate_office_extension_rejects_exe(self):
        with self.assertRaises(ValueError):
            validate_office_extension("bad.exe")

    def test_html_to_plain_text_strips_tags(self):
        plain = html_to_plain_text("<h1>Title</h1><p>Hello <b>world</b></p>")
        self.assertIn("Title", plain)
        self.assertIn("Hello", plain)
        self.assertIn("world", plain)
        self.assertNotIn("<", plain)


class KbDocsHubRouteTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)

    def test_docs_hub_requires_login(self):
        url = reverse("kb:kb_docs_hub")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url.lower())

    def test_office_upload_requires_login(self):
        url = reverse("kb:kb_office_upload")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    @mock.patch("apps.portal.views_kb_docs.import_writer_file_to_kb_article")
    def test_import_post_redirects_to_docs_hub(self, import_mock):
        from django.contrib.auth import get_user_model
        from apps.portal.models_kb import KBArticle, KBCategory

        import_mock.return_value = KBArticle(title="Test import", status="PENDING")
        user = get_user_model().objects.create_superuser(
            username="kb10x_import",
            email="kb10x_import@example.com",
            password="Test1234!",
        )
        category = KBCategory.objects.create(name="Guides 10x", slug="guides-10x")
        self.client.force_login(user)
        url = reverse("kb:kb_office_upload")
        response = self.client.post(
            url,
            {
                "action": "import_kb",
                "category": str(category.pk),
                "title": "Test import",
                "help_audience": "TENANT",
                "file": SimpleUploadedFile(
                    "note.txt",
                    b"Hello imported text for KB round-trip.",
                    content_type="text/plain",
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("docs-hub", response.url)
        import_mock.assert_called_once()
