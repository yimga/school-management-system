from django.test import SimpleTestCase
from apps.siteconfig.admin_surface_intelligence import build_admin_surface_profile

class AdminSurfaceIntelligenceTests(SimpleTestCase):
    def test_operator_is_stable_and_platform_scoped(self):
        profile = build_admin_surface_profile(user=object(), is_platform=True)
        self.assertEqual(profile["role_slug"], "operator")
        self.assertEqual(profile["tone"], "indigo")

    def test_known_tenant_roles_are_page_aware(self):
        for role, expected in (("PRINCIPAL", "principal"), ("BURSAR", "bursar"), ("REGISTRAR", "registrar")):
            user = type("User", (), {"role": role})()
            self.assertEqual(build_admin_surface_profile(user=user, is_platform=False)["role_slug"], expected)

    def test_unknown_or_hostile_role_degrades_to_admin(self):
        user = type("User", (), {"role": "<script>" * 100})()
        profile = build_admin_surface_profile(user=user, is_platform=False)
        self.assertEqual(profile["role_slug"], "admin")
        self.assertNotIn("<script>", profile["role_slug"])
