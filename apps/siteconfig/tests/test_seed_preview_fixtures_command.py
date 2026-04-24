"""Tests for seed_preview_fixtures management command (Phase B write contract)."""

from django.core.management import call_command
from django.test import TestCase

from apps.platform_runtime.helpers import get_platform_site_settings_record


class SeedPreviewFixturesCommandTests(TestCase):
    def test_seeds_portal_feed_and_footer_via_apply_feature_control_state(self):
        call_command("seed_preview_fixtures")

        site = get_platform_site_settings_record(create=False)
        self.assertIsNotNone(site)
        grades = site.portal_recent_grades
        self.assertEqual(len(grades), 3)
        self.assertEqual(grades[0]["label"], "Physics")
        self.assertEqual(len(site.portal_upcoming_assessments), 2)
        self.assertEqual(site.portal_upcoming_assessments[0]["title"], "Chemistry Test")
        self.assertEqual(len(site.portal_announcements), 2)
        self.assertEqual(len(site.portal_quick_actions), 3)
        badges = site.footer_badges
        self.assertEqual(len(badges), 2)
        self.assertEqual(badges[0]["label"], "Live Chat Ready")
