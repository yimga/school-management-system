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



    def test_admin_and_super_same_group_ids(self):

        admin_ids = [g.get("group_id") for g in build_manager_complete_sidebar_groups(self._req("/admin/"))]

        super_ids = [g.get("group_id") for g in build_manager_complete_sidebar_groups(self._req("/super/"))]

        self.assertEqual(admin_ids, super_ids)



    def test_complete_sidebar_has_cp_and_catalog_layers(self):
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

