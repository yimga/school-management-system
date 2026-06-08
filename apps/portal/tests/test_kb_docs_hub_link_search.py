from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.portal.kb_office_service import link_kb_article_to_office_document
from apps.portal.models_kb import HelpAudience, HostedOfficeDocument, KBArticle, KBCategory


class KbDocsHubUnifiedSearchTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.user = get_user_model().objects.create_superuser(
            username="kb_hub_search",
            email="kb_hub_search@example.com",
            password="Test1234!",
        )
        self.category = KBCategory.objects.create(name="Hub Search Cat", slug="hub-search-cat")
        self.article = KBArticle.objects.create(
            title="Unique Zephyr Runbook",
            slug="unique-zephyr-runbook",
            category=self.category,
            summary="Searchable summary for zephyr",
            content="Body about zephyr workflows",
            status="PUBLISHED",
            help_audience=HelpAudience.BOTH,
            author=self.user,
        )
        self.office_doc = HostedOfficeDocument.objects.create(
            title="Zephyr Office Template",
            file=SimpleUploadedFile("zephyr.odt", b"odt-bytes", content_type="application/vnd.oasis.opendocument.text"),
            help_audience=HelpAudience.BOTH,
            created_by=self.user,
        )

    def test_docs_hub_search_finds_article_and_office_doc(self):
        self.client.force_login(self.user)
        url = reverse("kb:kb_docs_hub")
        response = self.client.get(url, {"q": "zephyr"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unique Zephyr Runbook")
        self.assertContains(response, "Zephyr Office Template")

    def test_link_article_to_office_document_model_helper(self):
        link_kb_article_to_office_document(self.article, self.office_doc)
        self.article.refresh_from_db()
        self.assertEqual(self.article.linked_office_document_id, self.office_doc.pk)

    def test_link_post_via_docs_hub_route(self):
        self.client.force_login(self.user)
        url = reverse("kb:kb_link_office_document")
        response = self.client.post(
            url,
            {
                "article_id": str(self.article.pk),
                "office_document_id": str(self.office_doc.pk),
                "action": "link",
                "q": "zephyr",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("zephyr", response.url)
        self.article.refresh_from_db()
        self.assertEqual(self.article.linked_office_document_id, self.office_doc.pk)
