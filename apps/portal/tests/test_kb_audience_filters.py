from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.portal.kb_context import is_operator_help_request
from apps.portal.models_kb import FAQ, FAQCategory, HelpAudience, KBArticle, KBCategory
from apps.portal.views_kb import (
    _approved_faq_for_request,
    _published_kb_for_request,
    kb_article_download_pdf,
)
from apps.schools.models import School


User = get_user_model()


class KbAudienceFilterTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.user = User.objects.create_user(username="kbuser", password="pass")
        self.faq_cat = FAQCategory.objects.create(name="General", slug="general")
        self.kb_cat = KBCategory.objects.create(name="General", slug="general")

        FAQ.objects.create(category=self.faq_cat, question="Tenant Q", answer="A", status="APPROVED", help_audience=HelpAudience.TENANT)
        FAQ.objects.create(category=self.faq_cat, question="Operator Q", answer="A", status="APPROVED", help_audience=HelpAudience.OPERATOR)
        KBArticle.objects.create(category=self.kb_cat, title="Tenant Article", slug="tenant-article", summary="s", content="c", status="PUBLISHED", help_audience=HelpAudience.TENANT, author=self.user)
        KBArticle.objects.create(category=self.kb_cat, title="Operator Article", slug="operator-article", summary="s", content="c", status="PUBLISHED", help_audience=HelpAudience.OPERATOR, author=self.user)

    def _req(self, manager=False):
        req = self.rf.get("/kb/")
        req.user = self.user
        req.urlconf = "config.manager_urls" if manager else "config.tenant_urls"
        req.school = None
        req.META["REMOTE_ADDR"] = "127.0.0.1"
        return req

    def test_helper_detects_operator(self):
        self.assertTrue(is_operator_help_request(self._req(manager=True)))
        self.assertFalse(is_operator_help_request(self._req(manager=False)))

    def test_tenant_request_hides_operator_content(self):
        req = self._req(manager=False)
        self.assertEqual(set(_approved_faq_for_request(req).values_list("question", flat=True)), {"Tenant Q"})
        self.assertEqual(set(_published_kb_for_request(req).values_list("title", flat=True)), {"Tenant Article"})

    def test_operator_request_hides_tenant_content(self):
        req = self._req(manager=True)
        self.assertEqual(set(_approved_faq_for_request(req).values_list("question", flat=True)), {"Operator Q"})
        self.assertEqual(set(_published_kb_for_request(req).values_list("title", flat=True)), {"Operator Article"})

    def test_school_scoped_article_hidden_from_other_school(self):
        school_a = School.objects.create(
            name="Scope A",
            slug="scope-a",
            subdomain="scope-a",
            is_active=True,
        )
        school_b = School.objects.create(
            name="Scope B",
            slug="scope-b",
            subdomain="scope-b",
            is_active=True,
        )
        KBArticle.objects.create(
            category=self.kb_cat,
            title="Campus B only",
            slug="campus-b-only",
            summary="s",
            content="secret",
            status="PUBLISHED",
            help_audience=HelpAudience.TENANT,
            school=school_b,
            is_global_article=False,
            author=self.user,
        )
        req = self._req(manager=False)
        req.school = school_a
        titles = set(_published_kb_for_request(req).values_list("title", flat=True))
        self.assertNotIn("Campus B only", titles)

    def test_pdf_download_respects_school_scope(self):
        school_a = School.objects.create(
            name="Scope A2",
            slug="scope-a2",
            subdomain="scope-a2",
            is_active=True,
        )
        school_b = School.objects.create(
            name="Scope B2",
            slug="scope-b2",
            subdomain="scope-b2",
            is_active=True,
        )
        KBArticle.objects.create(
            category=self.kb_cat,
            title="B PDF",
            slug="b-pdf-only",
            summary="s",
            content="c",
            status="PUBLISHED",
            help_audience=HelpAudience.TENANT,
            school=school_b,
            is_global_article=False,
            author=self.user,
        )
        req = self._req(manager=False)
        req.school = school_a
        with self.assertRaises(Http404):
            kb_article_download_pdf(req, article_slug="b-pdf-only")
