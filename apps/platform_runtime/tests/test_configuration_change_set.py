from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.configuration_change_set import assert_change_set_fresh, generate_pack_change_set
from apps.schools.models import School


class ConfigurationChangeSetTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Change Set School", slug="change-set-school", subdomain="change-set-school", is_active=True, settings={})
        self.actor = User.objects.create_user(username="change_set_actor", password="x" * 8, role=User.Role.SUPERADMIN, is_staff=True)

    def test_change_set_generation_is_non_mutating(self):
        before = dict(self.school.settings or {})

        change_set = generate_pack_change_set("network-operator", pack_type="dashboard_pack", school=self.school, actor=self.actor, platform_operator=True)

        self.school.refresh_from_db()
        self.assertEqual(self.school.settings or {}, before)
        self.assertEqual(change_set["target_key"], "network-operator")
        self.assertTrue(change_set["requires_approval"])

    def test_stale_change_set_rejected(self):
        change_set = generate_pack_change_set("network-operator", pack_type="dashboard_pack", school=self.school, actor=self.actor, platform_operator=True)
        change_set["target_version"] = "0.0.0"

        with self.assertRaises(ValueError):
            assert_change_set_fresh(change_set)
