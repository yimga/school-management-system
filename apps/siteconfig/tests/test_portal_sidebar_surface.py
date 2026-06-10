"""Tenant ops/config sidebar split.

Verifies the portal sidebar separates day-to-day operations from platform
configuration: configuration sections sort to the bottom as one contiguous zone,
the two template builders are de-misfiled out of "Analytics & Reports", and the
operational workflow tools are un-buried out of the "Admin Panel" config zone.
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.portal_sidebar_items import (
    PORTAL_CONFIG_SECTIONS,
    _order_sections_ops_then_config,
    _portal_item_surface,
    build_portal_sidebar_items,
)

User = get_user_model()


class PortalSidebarSurfaceUnitTests(SimpleTestCase):
    """Pure-function contract — no DB."""

    def test_admin_panel_is_config_surface(self):
        self.assertEqual(_portal_item_surface("Admin Panel"), "config")

    def test_day_to_day_sections_are_ops_surface(self):
        for sec in (
            "Home",
            "Communication",
            "Learning Management",
            "Analytics & Reports",
            "Workflows & Approvals",
            "",
        ):
            self.assertEqual(_portal_item_surface(sec), "ops", msg=sec)

    def test_none_section_is_ops(self):
        self.assertEqual(_portal_item_surface(None), "ops")

    def test_order_pushes_config_sections_to_bottom(self):
        order = ["Home", "Admin Panel", "Communication", "Analytics & Reports"]
        self.assertEqual(
            _order_sections_ops_then_config(order),
            ["Home", "Communication", "Analytics & Reports", "Admin Panel"],
        )

    def test_order_preserves_ops_first_occurrence(self):
        order = ["Communication", "Home", "Admin Panel", "Learning Management"]
        result = _order_sections_ops_then_config(order)
        self.assertEqual(result[:3], ["Communication", "Home", "Learning Management"])


class PortalSidebarSplitIntegrationTests(TestCase):
    """Real assembled sidebar for a superuser on the portal (not backend)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.site = get_platform_site_settings_record(create=True)
        self.superuser = User.objects.create_superuser(
            username="sidebar_split_super",
            email="sidebar_split_super@example.com",
            password="test",
        )

    def _items(self, path="/portal/"):
        request = self.factory.get(path)
        request.user = self.superuser
        request.session = {}
        return build_portal_sidebar_items(request, self.site)

    def _by_id(self, items):
        return {it["id"]: it for it in items}

    def test_template_builders_demisfiled_to_config_zone(self):
        by_id = self._by_id(self._items())
        for cid in ("bulk_letters", "reportcard_builder"):
            self.assertIn(cid, by_id, msg=f"{cid} should be present for superuser")
            self.assertEqual(by_id[cid]["section"], "Admin Panel", msg=cid)
            self.assertEqual(by_id[cid]["surface"], "config", msg=cid)

    def test_operational_tools_unburied_to_ops_section(self):
        by_id = self._by_id(self._items())
        # workflow_center always renders (studio_os:automation reverses).
        self.assertIn("workflow_center", by_id)
        self.assertEqual(by_id["workflow_center"]["section"], "Workflows & Approvals")
        self.assertEqual(by_id["workflow_center"]["surface"], "ops")

    def test_all_admin_panel_items_are_config_surface(self):
        admin_items = [it for it in self._items() if it.get("section") == "Admin Panel"]
        self.assertTrue(admin_items, "expected Admin Panel items for superuser")
        for it in admin_items:
            self.assertEqual(it["surface"], "config", msg=it["id"])

    def test_config_zone_is_contiguous_and_last(self):
        items = self._items()
        surfaces = [it["surface"] for it in items]
        first_config = next((i for i, s in enumerate(surfaces) if s == "config"), None)
        self.assertIsNotNone(first_config, "expected a config zone for superuser")
        # No ops item appears after the config zone begins — config is one bottom block.
        self.assertTrue(
            all(s == "config" for s in surfaces[first_config:]),
            msg=f"config zone not contiguous/last: {[(it['id'], it['surface']) for it in items]}",
        )
        self.assertEqual(_portal_item_surface(items[-1].get("section")), "config")

    def test_access_identity_items_moved_to_config_zone(self):
        """RBAC / Staff Identity / Authentication Groups are access *configuration*,
        not a people roster — they belong in the config zone, not "People & Access"."""
        by_id = self._by_id(self._items())
        for cid in ("rbac", "tenant_identity", "groups"):
            if cid in by_id:  # gated items; assert only when present
                self.assertEqual(by_id[cid]["section"], "Admin Panel", msg=cid)
                self.assertEqual(by_id[cid]["surface"], "config", msg=cid)

    def test_people_access_keeps_only_rosters(self):
        """People & Access (ops) must not retain access-config items after the move."""
        people = {it["id"] for it in self._items() if it.get("section") == "People & Access"}
        self.assertFalse(
            people & {"rbac", "tenant_identity", "groups"},
            msg=f"People & Access still holds access-config items: {people}",
        )

    def test_analytics_section_has_no_config_items(self):
        analytics = [it for it in self._items() if it.get("section") == "Analytics & Reports"]
        for it in analytics:
            self.assertEqual(it["surface"], "ops", msg=it["id"])
            self.assertNotIn(it["id"], ("bulk_letters", "reportcard_builder"))
