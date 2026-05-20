"""KB draft generation requires evidence; no auto-publish."""

from __future__ import annotations

from django.test import SimpleTestCase

from services.ai_center.indexing import build_platform_index
from services.ai_center.kb_generator import generate_kb_article_from_route


class AICenterKBGenerationTests(SimpleTestCase):
    def setUp(self):
        build_platform_index()

    def test_kb_draft_from_known_route_has_evidence(self):
        from services.ai_center.indexing import index_document

        index_document(
            doc_id="route:/api-center/",
            text="API Center dashboard integrates webhooks and keys",
            module="apicenter",
            route="/api-center/",
        )
        draft = generate_kb_article_from_route("/api-center/", audience="operator")
        self.assertEqual(draft["status"], "draft")
        self.assertFalse(draft["tenant_visible"])
        self.assertTrue(draft["evidence_ids"])

    def test_kb_draft_without_evidence_rejected(self):
        with self.assertRaises(ValueError):
            generate_kb_article_from_route("/zzzz-no-such-route-xyz/")
