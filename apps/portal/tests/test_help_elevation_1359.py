"""Help center elevation wave (batch 1359)."""

from django.test import SimpleTestCase

from apps.portal.help_unified_hub import operator_public_kb_lane, tenant_community_lane
from apps.portal.marketing_kb import marketing_kb_search_hybrid


class HelpElevation1359Tests(SimpleTestCase):
    def test_operator_public_kb_lane_urls(self):
        lane = operator_public_kb_lane()
        self.assertIn("marketing_search_url", lane)
        self.assertTrue(
            lane["marketing_search_url"] is None
            or "/resources/help-center/search/" in lane["marketing_search_url"]
        )

    def test_hybrid_search_empty_query(self):
        hits, mode = marketing_kb_search_hybrid("")
        self.assertEqual(hits, [])
        self.assertEqual(mode, "text")

    def test_tenant_community_lane_anonymous(self):
        from django.test import RequestFactory

        req = RequestFactory().get("/")
        req.user = type("U", (), {"is_authenticated": False})()
        req.school = None
        self.assertFalse(tenant_community_lane(req)["visible"])
