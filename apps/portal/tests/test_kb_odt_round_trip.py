"""KB ODT round-trip — staff re-import on published articles (batch 1647)."""
from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.portal.kb_office_service import reimport_odt_into_kb_article
from apps.portal.models_kb import HelpAudience, KBArticle, KBCategory


class KbOdtRoundTripServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_superuser(
            username="kb_rt_staff",
            email="kb_rt_staff@example.com",
            password="Test1234!",
        )
        self.category = KBCategory.objects.create(name="Round trip", slug="round-trip")
        self.article = KBArticle.objects.create(
            category=self.category,
            title="Published guide",
            slug="published-guide",
            summary="Original summary",
            content="Original body text for round-trip test.",
            author=self.staff,
            status="PUBLISHED",
            help_audience=HelpAudience.OPERATOR,
            is_global_article=True,
        )

    def test_reimport_updates_same_article_and_sets_updated_status(self):
        upload = SimpleUploadedFile(
            "edited.txt",
            b"Revised body after offline LibreOffice edit.",
            content_type="text/plain",
        )
        pk_before = self.article.pk
        updated = reimport_odt_into_kb_article(
            self.article,
            uploaded_file=upload,
            author=self.staff,
        )
        self.assertEqual(updated.pk, pk_before)
        self.assertEqual(updated.status, "UPDATED")
        self.assertIn("Revised body", updated.content)


class KbOdtRoundTripViewTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        user_model = get_user_model()
        self.staff = user_model.objects.create_superuser(
            username="kb_rt_view_staff",
            email="kb_rt_view@example.com",
            password="Test1234!",
        )
        self.other = user_model.objects.create_user(
            username="kb_rt_parent",
            email="kb_rt_parent@example.com",
            password="Test1234!",
        )
        self.category = KBCategory.objects.create(name="RT views", slug="rt-views")
        self.article = KBArticle.objects.create(
            category=self.category,
            title="View round trip",
            slug="view-round-trip",
            summary="Summary",
            content="Body",
            author=self.staff,
            status="PUBLISHED",
            help_audience=HelpAudience.OPERATOR,
            is_global_article=True,
        )

    def test_reimport_requires_staff(self):
        self.client.force_login(self.other)
        url = reverse("kb:kb_article_reimport_odt", kwargs={"article_slug": self.article.slug})
        response = self.client.post(
            url,
            {
                "file": SimpleUploadedFile(
                    "note.txt",
                    b"Should not apply",
                    content_type="text/plain",
                ),
            },
        )
        self.assertIn(response.status_code, (302, 403))
        self.article.refresh_from_db()
        self.assertEqual(self.article.status, "PUBLISHED")
        self.assertEqual(self.article.content, "Body")

    def test_staff_reimport_post_redirects_and_updates(self):
        self.client.force_login(self.staff)
        url = reverse("kb:kb_article_reimport_odt", kwargs={"article_slug": self.article.slug})
        response = self.client.post(
            url,
            {
                "file": SimpleUploadedFile(
                    "note.txt",
                    b"Staff upload revision text.",
                    content_type="text/plain",
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.article.slug, response.url)
        self.article.refresh_from_db()
        self.assertEqual(self.article.status, "UPDATED")
        self.assertIn("Staff upload revision", self.article.content)


class KbOdtRegenerateTests(TestCase):
    def test_regenerate_kb_article_odt_attaches_file(self):
        from apps.portal.kb_office_service import regenerate_kb_article_odt

        user_model = get_user_model()
        staff = user_model.objects.create_superuser(
            username="kb_regen_staff",
            email="kb_regen@example.com",
            password="Test1234!",
        )
        category = KBCategory.objects.create(name="Regen", slug="regen")
        article = KBArticle.objects.create(
            category=category,
            title="Regen guide",
            slug="regen-guide",
            content="# Heading\n\nBody for ODT regeneration.",
            author=staff,
            status="PUBLISHED",
            help_audience=HelpAudience.OPERATOR,
            is_global_article=True,
        )
        with mock.patch(
            "apps.portal.kb_office_service.markdown_to_document",
            return_value=b"fake-odt-bytes",
        ):
            self.assertTrue(regenerate_kb_article_odt(article))
        article.refresh_from_db()
        self.assertTrue(article.odt_file)
