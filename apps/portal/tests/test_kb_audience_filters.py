from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.portal.kb_context import is_operator_help_request
from apps.portal.models_kb import FAQ, FAQCategory, HelpAudience, KBArticle, KBCategory
from apps.portal.views_kb import _approved_faq_for_request, _published_kb_for_request


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
