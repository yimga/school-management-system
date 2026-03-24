"""Primary horizontal nav (Wave 1) — no DB."""

from django.test import RequestFactory, SimpleTestCase

from apps.schools.control_plane_nav import build_primary_control_plane_nav


class PrimaryControlPlaneNavTests(SimpleTestCase):
    """build_primary_control_plane_nav resolves 8 pills on manager urlconf."""

    def test_eight_pills_stable_order(self):
        request = RequestFactory().get("/super/dashboard/")
        request.urlconf = "config.manager_urls"
        primary = build_primary_control_plane_nav(request)
        ids = [x["id"] for x in primary]
        self.assertEqual(len(primary), 8, msg=ids)
        self.assertEqual(
            ids,
            [
                "primary_home",
                "primary_studio",
                "primary_operations",
                "primary_marketplace",
                "primary_analytics",
                "primary_migration",
                "primary_support",
                "primary_control",
            ],
        )

    def test_current_flag_studio_vs_control(self):
        req_studio = RequestFactory().get("/studio/experience/")
        req_studio.urlconf = "config.manager_urls"
        ps = {x["id"]: x for x in build_primary_control_plane_nav(req_studio)}
        self.assertTrue(ps["primary_studio"]["is_current"])
        self.assertFalse(ps["primary_control"]["is_current"])

        req_ctl = RequestFactory().get("/studio/control/")
        req_ctl.urlconf = "config.manager_urls"
        pc = {x["id"]: x for x in build_primary_control_plane_nav(req_ctl)}
        self.assertFalse(pc["primary_studio"]["is_current"])
        self.assertTrue(pc["primary_control"]["is_current"])
