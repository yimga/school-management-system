"""Tenant v3 extended cockpit realdata hydration (batch 1615)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.accounts.models import User
from apps.siteconfig.cockpit_tenant_v3_realdata import (
    _hydrate_ai_study_buddy,
    _hydrate_financial_timeline,
    hydrate_tenant_v3_extended_realdata,
)


class TenantV3ExtendedRealdataTests(SimpleTestCase):
    def test_financial_timeline_hydrates_from_widget_finance(self):
        section = {"enabled": False, "events": [], "a8_wire_pending": True}
        widget = {"finance": {"balance": Decimal("125.00"), "overdue": 2}}
        out = _hydrate_financial_timeline(section, widget)
        self.assertTrue(out["enabled"])
        self.assertEqual(out["balance_display"], "125.00")
        self.assertFalse(out["a8_wire_pending"])

    @patch("apps.portal.tenant_cockpit_realdata._role_widget_bundle")
    def test_hydrate_extended_merges_financial_timeline(self, mock_bundle):
        mock_bundle.return_value = {
            "finance": {"balance": Decimal("0.00"), "overdue": 0},
        }
        rf = RequestFactory()
        request = rf.get("/portal/parent/")
        request.user = type("U", (), {"role": User.Role.PARENT, "pk": 1})()
        cockpit = {
            "financial_timeline": {"enabled": False, "events": []},
            "gradebook_trend": {"enabled": False, "subjects": []},
        }
        out = hydrate_tenant_v3_extended_realdata(request, cockpit)
        self.assertTrue(out["financial_timeline"]["enabled"])

    def test_ai_study_buddy_links_copilot_for_student(self):
        rf = RequestFactory()
        request = rf.get("/portal/student/")
        request.user = type("U", (), {"role": User.Role.STUDENT, "pk": 2})()
        section = {"enabled": False, "suggestions": [], "a8_wire_pending": True}
        out = _hydrate_ai_study_buddy(request, section)
        self.assertTrue(out["enabled"])
        self.assertFalse(out["a8_wire_pending"])
        self.assertGreaterEqual(len(out["suggestions"]), 1)
