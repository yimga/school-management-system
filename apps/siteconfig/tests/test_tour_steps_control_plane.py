"""BR-13: control-plane tour steps (no DB for step list logic)."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.siteconfig.views_tour import control_plane_default_tour_steps


class TourStepsControlPlaneTests(SimpleTestCase):
    def test_super_trust_for_superuser(self):
        u = SimpleNamespace(is_authenticated=True, is_superuser=True, role="")
        steps = control_plane_default_tour_steps("super_trust", u)
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0]["code"], "cp-trust-header")

    def test_super_migration_steps(self):
        u = SimpleNamespace(is_authenticated=True, is_superuser=True, role="")
        steps = control_plane_default_tour_steps("super_migration", u)
        self.assertEqual(len(steps), 2)

    def test_empty_for_anonymous(self):
        u = SimpleNamespace(is_authenticated=False)
        self.assertEqual(control_plane_default_tour_steps("super_trust", u), [])
