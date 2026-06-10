"""Manager complete sidebar nav (batch 1500)."""



from django.test import RequestFactory, SimpleTestCase



from apps.schools.manager_nav_convergence import (

    build_manager_complete_sidebar_groups,

    build_manager_unified_sidebar_groups,

)





class ManagerNavConvergenceTests(SimpleTestCase):

    def _req(self, path: str):
        from django.contrib.auth import get_user_model

        request = RequestFactory().get(path)
        request.urlconf = "config.manager_urls"
        request.user = get_user_model()(is_superuser=True, username="nav_test")
        return request



    def test_complete_sidebar_includes_unified_head(self):

        complete = build_manager_complete_sidebar_groups(self._req("/super/"))

        ids = [g.get("group_id") for g in complete[:2]]

        self.assertEqual(ids, ["unified_start", "unified_guided_setup"])



    def test_admin_and_super_surfaces_diverge(self):
        """/super/ renders day-to-day (ops) groups; manager /admin/ renders
        configuration groups. The shared Start + Guided head crosses both, but
        the control-plane spine below it must NOT be identical anymore."""
        admin_labels = [g.get("label") for g in build_manager_complete_sidebar_groups(self._req("/admin/"))]
        super_labels = [g.get("label") for g in build_manager_complete_sidebar_groups(self._req("/super/"))]

        # Day-to-day group lives on /super/ only.
        self.assertIn("Platform Overview", super_labels)
        self.assertNotIn("Platform Overview", admin_labels)
        # Configuration group lives on manager /admin/ only.
        self.assertIn("Tenant config defaults", admin_labels)
        self.assertNotIn("Tenant config defaults", super_labels)
        # Both still share the cross-surface Start head.
        self.assertEqual(super_labels[0], admin_labels[0])

    def test_super_surface_drops_admin_model_catalog(self):
        """The /super/ day-to-day spine must not carry the Django admin model
        catalog firehose (the "Backoffice · …" groups)."""
        super_labels = [
            str(g.get("label") or "")
            for g in build_manager_complete_sidebar_groups(self._req("/super/"))
        ]
        self.assertFalse(
            any(lbl.startswith("Backoffice · ") for lbl in super_labels),
            msg=f"/super/ should not include catalog groups: {super_labels}",
        )

    def test_config_tool_under_super_follows_config_spine(self):
        """Configuration tools are served under /super/* (e.g. /super/blueprints/);
        the sidebar must follow the page to the config spine rather than strand it
        on the ops sidebar with no matching nav item."""
        from django.urls import reverse

        url = reverse("super:blueprints_catalog", urlconf="config.manager_urls")
        labels = [
            g.get("label")
            for g in build_manager_complete_sidebar_groups(self._req(url))
        ]
        self.assertIn("Blueprints & Policies", labels)  # config group present
        self.assertNotIn("Platform Overview", labels)  # ops group hidden on a config page



    def test_super_surface_has_ops_cp_layer(self):
        complete = build_manager_complete_sidebar_groups(self._req("/super/"))
        labels = [g.get("label") for g in complete]
        self.assertIn("Platform Overview", labels)
        self.assertGreaterEqual(len(complete), 4)

    def test_complete_sidebar_dedupes_repeated_group_labels(self):
        complete = build_manager_complete_sidebar_groups(self._req("/super/"))
        labels = [str(g.get("label") or "").casefold() for g in complete]
        self.assertEqual(len(labels), len(set(labels)))
        for group in complete:
            keys = [
                str(item.get("id") or item.get("url") or item.get("label") or "").casefold()
                for item in group.get("items") or []
            ]
            self.assertEqual(len(keys), len(set(keys)), msg=group.get("label"))



    def test_unified_groups_unchanged(self):

        groups = build_manager_unified_sidebar_groups(self._req("/super/"))

        self.assertEqual(len(groups), 2)

