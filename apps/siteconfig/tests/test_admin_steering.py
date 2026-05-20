"""Unified admin steering strip + index KPI helpers."""

from django.test import RequestFactory, SimpleTestCase

from apps.siteconfig.admin_steering import (
    build_admin_index_kpi_strip,
    build_admin_steering_hint,
)


class AdminSteeringTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_siteconfig_changelist_gets_steering_hint(self):
        request = self.rf.get("/admin/siteconfig/sitesettings/")
        hint = build_admin_steering_hint(request, is_platform_site=True)
        self.assertIsNotNone(hint)
        self.assertEqual(hint["hint_id"], "siteconfig")
        self.assertGreaterEqual(len(hint["links"]), 2)

    def test_non_changelist_path_has_no_hint(self):
        request = self.rf.get("/admin/siteconfig/sitesettings/add/")
        self.assertIsNone(build_admin_steering_hint(request, is_platform_site=True))

    def test_index_kpi_strip_from_dashboard_context(self):
        ctx = {
            "can_see_user_stats": True,
            "can_see_sessions": True,
            "can_see_compliance": True,
            "total_users": 10,
            "admin_count": 2,
            "active_sessions": 3,
            "sessions_24h": 5,
            "security_alerts_24h": 0,
            "access_denials_24h": 1,
            "new_logins_24h": 4,
            "failed_logins_24h": 0,
            "pending_approvals_count": 0,
        }
        kpis = build_admin_index_kpi_strip(ctx)
        labels = {k["label"] for k in kpis}
        self.assertIn("Users", labels)
        self.assertIn("Active sessions", labels)
