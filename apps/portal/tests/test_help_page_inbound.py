"""Tests for page-aware help center inbound params."""

from django.test import RequestFactory, SimpleTestCase

from apps.portal.help_page_inbound import (
    feature_form_initial_from_request,
    parse_help_landing_inbound,
)


class HelpPageInboundTests(SimpleTestCase):
    def test_parse_q_and_active_url(self):
        request = RequestFactory().get(
            "/help-center/",
            {
                "from": "page_help",
                "active_url": "/super/billing/",
                "q": "How do I use Billing?",
            },
        )
        ctx = parse_help_landing_inbound(request)
        self.assertEqual(ctx["page_help_active_url"], "/super/billing/")
        self.assertTrue(ctx["page_help_from_landing"])
        self.assertEqual(ctx["help_search_initial_q"], "How do I use Billing?")

    def test_segment_hint_when_q_missing(self):
        request = RequestFactory().get(
            "/help/",
            {"from": "page_help", "active_url": "/super/tenant-health/"},
        )
        ctx = parse_help_landing_inbound(request)
        self.assertEqual(ctx["help_search_initial_q"], "tenant health")

    def test_feature_form_initial_merges_title(self):
        request = RequestFactory().get(
            "/help-center/",
            {"from": "page_help", "q": "Import students"},
        )
        initial = feature_form_initial_from_request(request, {"affected_roles": "ADMIN"})
        self.assertEqual(initial["title"], "Import students")
